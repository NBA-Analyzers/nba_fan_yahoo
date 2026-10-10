from datetime import date
from types import SimpleNamespace

import pytest

from appl.ai.document_indexer import DocumentIndexer
from appl.ai.retrieval import RetrievalService
from appl.fantasy_integrations.yahoo.sync_league.sync_yahoo_league import (
    YahooLeague,
    parse_matchups,
)
from appl.fantasy_integrations.yahoo.sync_league.yahoo_tokens import (
    TokenRefreshError,
    ensure_fresh,
    load_saved_entry,
    save_entry,
)
from appl.ingest.http import RateLimiter, with_retry
from appl.ingest.jobs import general_index
from appl.ingest.player_report import build_player_report
from appl.ingest.schemas import SeasonLine, TooManyRejected, validate_rows
from appl.ingest.season import current_season, previous_season, season_end, yahoo_game_year
from appl.ingest.sinks.datasets import LocalDatasetStore
from appl.ingest.sources.nba import NbaSource


# --- season -------------------------------------------------------------------

@pytest.mark.parametrize("today, season", [
    (date(2026, 6, 30), "2025-26"),
    (date(2026, 7, 1), "2026-27"),
    (date(2026, 10, 9), "2026-27"),
    (date(2027, 3, 1), "2026-27"),
    (date(2099, 12, 1), "2099-00"),
])
def test_current_season_rolls_over_in_july(today, season):
    assert current_season(today) == season


def test_season_helpers():
    assert previous_season("2026-27") == "2025-26"
    assert previous_season("2026-27", 2) == "2024-25"
    assert season_end("2026-27") == date(2027, 4, 30)
    assert yahoo_game_year("2026-27") == 2026
    with pytest.raises(ValueError):
        previous_season("nope")


# --- retries and rate limiting ----------------------------------------------------

def test_with_retry_backs_off_then_succeeds():
    waits, calls = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("down")
        return "ok"

    assert with_retry(flaky, attempts=3, delay=1.0, sleep=waits.append) == "ok"
    assert waits == [1.0, 2.0]


def test_with_retry_gives_up_and_ignores_other_errors():
    with pytest.raises(ConnectionError):
        with_retry(lambda: (_ for _ in ()).throw(ConnectionError()), attempts=2, sleep=lambda s: None)
    calls = []

    def bad():
        calls.append(1)
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        with_retry(bad, retry_on=(ConnectionError,), sleep=lambda s: None)
    assert len(calls) == 1


def test_rate_limiter_spaces_calls():
    clock = [0.0]
    waits = []

    def sleep(s):
        waits.append(s)
        clock[0] += s

    limiter = RateLimiter(0.5, clock=lambda: clock[0], sleep=sleep)
    limiter.wait()
    limiter.wait()
    clock[0] += 2.0
    limiter.wait()
    assert waits == [0.5]


# --- validation -------------------------------------------------------------------

def test_validate_rows_drops_bad_rows_and_fails_on_too_many():
    good = {"nba_id": 1, "name": "A", "GP": 10}
    rows = validate_rows(SeasonLine, [good] * 9 + [{"nba_id": 2, "GP": -1}], source="t")
    assert len(rows) == 9
    with pytest.raises(TooManyRejected):
        validate_rows(SeasonLine, [good, {"name": ""}, {"GP": "x"}], source="t")


# --- NBA source -----------------------------------------------------------------------

def _dash(pid, name, gp=10, pts=20.0, **extra):
    return {"PLAYER_ID": pid, "PLAYER_NAME": name, "TEAM_ABBREVIATION": "LAL", "GP": gp,
            "MIN": 30.0, "PTS": pts, "REB": 5.0, "AST": 5.0, "STL": 1.0, "BLK": 0.5,
            "TOV": 2.0, "FG3M": 2.0, "FGM": 8.0, "FGA": 16.0, "FG_PCT": 0.5, "FTM": 3.0,
            "FTA": 4.0, "FT_PCT": 0.75, **extra}


class FakeNbaApi:
    def __init__(self):
        self.calls = []
        self.dash = {"2026-27": [_dash(1, "Joe Smith", pts=25.0)],
                     "2025-26": [_dash(1, "Joe Smith"), _dash(2, "Old Timer")]}
        self.days = {"2026-10-21": [{"game_id": "g1", "home_team": "Lakers", "away_team": "Suns"}]}
        self.failing_days = set()

    def league_dash(self, season):
        self.calls.append(("dash", season))
        return self.dash.get(season, [])

    def game_logs(self, season, since):
        self.calls.append(("logs", season))
        return [{"PLAYER_ID": 1, "GAME_DATE": "2026-10-08T00:00:00", "MIN": 34, "PTS": 30,
                 "REB": 4, "AST": 6, "STL": 1, "BLK": 0, "TOV": 3, "FG_PCT": 0.55,
                 "FT_PCT": 0.9, "FG3M": 4, "FGM": 11, "FGA": 20, "FTM": 4, "FTA": 4}]

    def scoreboard(self, day):
        self.calls.append(("scoreboard", day))
        if day in self.failing_days:
            raise ConnectionError("timeout")
        return self.days.get(day, [])


@pytest.fixture
def nba():
    api = FakeNbaApi()
    return NbaSource(limiter=RateLimiter(0), sleep=lambda s: None, api=api), api


def test_league_dash_is_fetched_once_per_season(nba):
    source, api = nba
    source.league_dash("2026-27")
    source.season_lines("2026-27")
    assert api.calls.count(("dash", "2026-27")) == 1


def test_season_lines_are_in_pool_shape(nba):
    source, _ = nba
    line = source.season_lines("2026-27")[1]
    assert line["name"] == "Joe Smith" and line["PTS"] == 25.0 and line["team"] == "LAL"


def test_schedule_dedupes_and_skips_failed_days(nba):
    source, api = nba
    api.days["2026-10-22"] = api.days["2026-10-21"]  # same game id reported twice
    api.failing_days.add("2026-10-23")
    games = source.schedule(date(2026, 10, 21), date(2026, 10, 23))
    assert games == [{"game_id": "g1", "date": "2026-10-21", "home_team": "Lakers", "away_team": "Suns"}]


# --- player report ------------------------------------------------------------------

def test_player_report_combines_season_last_season_and_windows():
    api = FakeNbaApi()
    report = build_player_report(api.dash["2026-27"], api.dash["2025-26"],
                                 api.game_logs("2026-27", None), today=date(2026, 10, 9))
    assert set(report) == {"Joe Smith", "Old Timer"}
    joe = report["Joe Smith"]
    assert joe["season"]["Points"] == 25.0 and joe["last_season"]["Points"] == 20.0
    assert joe["last_7_days"]["Games Played"] == 1 and joe["last_7_days"]["Points"] == 30.0
    assert report["Old Timer"]["season"] is None and report["Old Timer"]["last_7_days"] is None


# --- general index job ---------------------------------------------------------------

@pytest.fixture
def indexer(embedder, memory_store):
    return DocumentIndexer(RetrievalService(embedder, memory_store),
                           pdf_extractor=lambda path: "rules text")


def test_general_index_fills_each_collection_and_skips_when_unchanged(nba, indexer, memory_store, tmp_path):
    source, _ = nba
    datasets = LocalDatasetStore(tmp_path)
    memory_store.replace_collection("general", [])  # legacy collection

    first = general_index.run(indexer, datasets, nba=source, today=date(2026, 10, 20),
                              rules_pdf=tmp_path / "rules.pdf")
    assert first["stats"] == {"players": 2, "indexed": True}
    assert first["schedule"] == {"games": 1, "indexed": True}
    assert first["rules"] == {"indexed": True}
    assert datasets.get("player_stats_2026-27") and datasets.get("schedule_2026-27")
    assert memory_store.last_synced("general") is None

    second = general_index.run(indexer, datasets, nba=source, today=date(2026, 10, 20),
                               rules_pdf=tmp_path / "rules.pdf")
    assert not any(second[k]["indexed"] for k in ("stats", "schedule", "rules"))


def test_general_index_keeps_old_data_when_a_source_is_empty(nba, indexer, memory_store, tmp_path):
    source, api = nba
    general_index.run(indexer, LocalDatasetStore(tmp_path), nba=source,
                      today=date(2026, 10, 20), rules_pdf=tmp_path / "r.pdf")
    api.days.clear()
    source = NbaSource(limiter=RateLimiter(0), sleep=lambda s: None, api=api)
    result = general_index.run(indexer, LocalDatasetStore(tmp_path), nba=source,
                               today=date(2026, 10, 20), rules_pdf=tmp_path / "r.pdf")
    assert result["schedule"] == {"games": 0, "indexed": False}
    assert memory_store.search(["general_schedule"], [1.0] + [0.0] * 31, k=5)


# --- Yahoo matchups -----------------------------------------------------------------

def _team(key, name, points, stats=()):
    return {"team": [[{"team_key": key}, {"name": name}],
                     {"team_points": {"total": points},
                      "team_stats": {"stats": [{"stat": {"stat_id": sid, "value": v}} for sid, v in stats]}}]}


def _matchup(week, a, b, **extra):
    return {"matchup": {"week": week, "0": {"teams": {"0": a, "1": b}}, **extra}}


def test_matchup_winner_is_the_higher_score_either_side():
    parsed = {"0": _matchup(1, _team("t.1", "A", "4"), _team("t.2", "B", "5")),
              "1": _matchup(1, _team("t.3", "C", "6"), _team("t.4", "D", "3")),
              "count": 2}
    winners = [m["team_win_name"] for m in parse_matchups(parsed)]
    assert winners == ["B", "C"]


def test_matchup_uses_yahoo_winner_and_tie_flags():
    parsed = {"0": _matchup(2, _team("t.1", "A", "5"), _team("t.2", "B", "4"), winner_team_key="t.2"),
              "1": _matchup(2, _team("t.3", "C", "5"), _team("t.4", "D", "5"), is_tied=1)}
    assert [m["team_win_name"] for m in parse_matchups(parsed)] == ["B", "Finished in a draw"]


def test_matchup_keeps_unknown_stats_and_skips_one_team_matchups():
    parsed = {"0": _matchup(1, _team("t.1", "A", "4", [("12", "100"), ("999", "7")]),
                            _team("t.2", "B", "5")),
              "1": {"matchup": {"week": 1, "0": {"teams": {"0": _team("t.3", "C", "1")}}}}}
    [m] = parse_matchups(parsed)
    assert m["team_1"]["stats"] == {"Points": "100", "stat_999": "7"}


class FakeLeague:
    league_id = "L1"

    def __init__(self, broken=()):
        self.broken = set(broken)

    def _maybe(self, name, value):
        if name in self.broken:
            raise RuntimeError(f"{name} down")
        return value

    def settings(self):
        return self._maybe("settings", {"name": "L", "start_week": "1", "end_week": "3"})

    def standings(self):
        return self._maybe("standings", [{"team": "A"}])

    def current_week(self):
        return 2

    def matchups(self, week):
        return {"fantasy_content": {"league": [{}, {"scoreboard": {"0": {"matchups": {
            "0": _matchup(week, _team("t.1", "A", "1"), _team("t.2", "B", "2"))}}}}]}}

    def free_agents(self, position):
        return self._maybe("free_agents", [])

    def teams(self):
        return {"t.1": {"name": "A"}}

    def to_team(self, key):
        league = self

        class Team:
            def roster(self):
                return league._maybe("roster", [{"name": "Joe"}])

        return Team()


class RecordingStorage:
    def __init__(self):
        self.names = []

    def upload_json_with_retries(self, data, blob_name, max_retries=4):
        self.names.append(blob_name)
        return True


def test_full_sync_uses_league_weeks_and_reports_failures():
    storage = RecordingStorage()
    league = YahooLeague(FakeLeague(broken={"free_agents"}), sleep=lambda s: None)
    results = league.sync_full_league(storage)
    assert set(results) == {"league_settings", "standings", "matchups", "team_rosters"}
    assert len(results["matchups"]) == 2  # weeks 1..current week (2), not a fixed 20
    assert league.failed == ["free_agents"] and league.critical_ok


def test_full_sync_is_not_fresh_when_a_critical_part_fails():
    league = YahooLeague(FakeLeague(broken={"roster"}), sleep=lambda s: None)
    league.sync_full_league(RecordingStorage())
    assert "team_rosters" in league.failed and not league.critical_ok


# --- Yahoo token refresh ------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


def test_fresh_tokens_are_left_alone():
    entry = {"access_token": "a", "refresh_token": "r", "expires_at": 10_000}
    assert ensure_fresh(entry, now=1_000, post=lambda *a, **k: pytest.fail("no call")) is False


def test_expiring_token_is_refreshed_in_place():
    entry = {"access_token": "old", "refresh_token": "r", "expires_at": 1_050}
    sent = {}

    def post(url, auth, data, timeout):
        sent.update(data)
        return FakeResponse(200, {"access_token": "new", "refresh_token": "r2", "expires_in": 3600})

    assert ensure_fresh(entry, now=1_000, post=post) is True
    assert entry == {"access_token": "new", "refresh_token": "r2", "expires_at": 4_600}
    assert sent["grant_type"] == "refresh_token" and sent["refresh_token"] == "r"


def test_failed_refresh_raises():
    entry = {"access_token": "old", "refresh_token": "r", "expires_at": 0}
    with pytest.raises(TokenRefreshError):
        ensure_fresh(entry, now=1_000, post=lambda *a, **k: FakeResponse(401))


class FakeFantasy:
    def __init__(self, yahoo_id):
        self.yahoo_id = yahoo_id

    def get_yahoo_user_id_for_google_user(self, google_user_id):
        return self.yahoo_id


class FakeAuth:
    def __init__(self):
        self.saved = []

    def get_yahoo_user(self, yahoo_user_id):
        return SimpleNamespace(access_token="a", refresh_token="r", username="uri")

    def update_yahoo_tokens(self, *args):
        self.saved.append(args)


def test_saved_tokens_are_restored_and_refreshed_on_first_use():
    entry = load_saved_entry("g-1", fantasy=FakeFantasy("y-1"), auth=FakeAuth())
    assert entry == {"access_token": "a", "refresh_token": "r", "expires_at": 0,
                     "guid": "y-1", "username": "uri"}


def test_nothing_to_restore_without_a_yahoo_connection():
    assert load_saved_entry("g-1", fantasy=FakeFantasy(None), auth=FakeAuth()) is None


def test_refreshed_tokens_are_saved():
    auth = FakeAuth()
    save_entry({"guid": "y-1", "access_token": "new", "refresh_token": "r2"}, auth=auth)
    assert auth.saved == [("y-1", "new", "r2")]
