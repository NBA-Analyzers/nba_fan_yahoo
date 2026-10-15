"""Head-to-head scoring, lineup eligibility, injury weighting, the player-status feeds and
the chat toolkit for every league type."""

import json
from datetime import date
from types import SimpleNamespace as NS

import pytest

from appl.ai.tools import Toolkit, league_toolkit_factory
from appl.draft.manual_league import ManualLeagueStore
from appl.draft.ranker import DraftRanker, unsupported_categories
from appl.ingest.jobs import player_status as status_job
from appl.ingest.sinks.datasets import LocalDatasetStore
from appl.ingest.sources import espn_status
from appl.season import player_status, snapshot as snapshots
from appl.season.analyzer import SeasonAnalyzer
from appl.season.player_status import PlayerData
from appl.season.schedule import Schedule
from appl.tests.unit.test_draft import _name, _player
from appl.fantasy_integrations.espn import espn_league_info
from appl.season.analyzer import _add
from appl.tests.unit.test_espn import SWID, rich_league
from appl.tests.unit.test_season import USER, _drafted_league

TODAY = date(2026, 11, 2)  # a Monday


def pool_with_positions():
    bigs = [{**_player(_name("Big", i), True, i), "pos": "C"} for i in range(40)]
    guards = [{**_player(_name("Guard", i), False, 100 + i), "pos": "PG"} for i in range(60)]
    return bigs + guards


@pytest.fixture(scope="module")
def ranker():
    return DraftRanker(pool_with_positions(), num_teams=4, roster_size=3)


def league(ranker, scoring="roto", slots=None, injuries=None, me=0):
    names = {p["name"] for p in ranker.players}
    bigs = sorted(n for n in names if n.startswith("Big"))
    guards = sorted(n for n in names if n.startswith("Guard"))
    rosters = [[bigs[0], guards[0], guards[1]], [bigs[1], guards[2], guards[3]],
               [bigs[2], bigs[3], guards[4]], [bigs[4], guards[5], guards[6]]]
    return snapshots.LeagueSnapshot(
        "t", "L", ranker.categories, [f"T{i}" for i in range(4)], me, rosters,
        slots=slots or {}, injuries=injuries or {}, scoring=scoring), rosters


# ---------- head-to-head objective ----------
def test_roto_score_stays_whole_points(ranker):
    snap, _ = league(ranker)
    analyzer = SeasonAnalyzer(ranker, snap)
    assert isinstance(analyzer._my_points(), int)
    assert analyzer.report()["objective"] == "roto_points"


def test_h2h_score_is_expected_category_wins(ranker):
    snap, _ = league(ranker, scoring="h2h")
    analyzer = SeasonAnalyzer(ranker, snap)
    score = analyzer._my_points()
    assert 0 < score < len(analyzer.counted)
    report = analyzer.report()
    assert report["objective"] == "expected_category_wins" and report["scoring"] == "h2h"
    assert all(isinstance(p["points_gain"], float) for p in report["pickups"])


def test_beat_probability_is_symmetric_and_respects_turnovers(ranker):
    snap, _ = league(ranker, scoring="h2h")
    a = SeasonAnalyzer(ranker, snap)
    assert a._beat_prob("PTS", 100, 100) == pytest.approx(0.5)
    assert a._beat_prob("PTS", 110, 100) > 0.5 > a._beat_prob("PTS", 90, 100)
    assert a._beat_prob("TO", 90, 100) > 0.5  # fewer turnovers wins
    assert a._beat_prob("PTS", 110, 100) + a._beat_prob("PTS", 100, 110) == pytest.approx(1.0)


def test_h2h_pickups_treat_near_equal_gains_as_ties(ranker):
    snap, _ = league(ranker, scoring="h2h")
    a = SeasonAnalyzer(ranker, snap)
    fa = ranker.find("Guard Ba")
    keep_a, keep_b = a.players[a.me][0], a.players[a.me][1]
    a.players[a.me] = [keep_a, keep_b]
    a._free_agents = lambda limit=None: [fa]
    gains = {  # dropping A gains a hair more, but B is the better player to let go
        _add(_add(a.totals[a.me], a._aline(keep_a), -1), a._aline(fa)): 0.004,
        _add(_add(a.totals[a.me], a._aline(keep_b), -1), a._aline(fa)): 0.003,
    }
    a._my_points = lambda changes=None: gains[changes[a.me]] if changes else 0.0
    values = {fa["key"]: 0.0, keep_a["key"]: 2.0, keep_b["key"]: -1.0}
    a._value = lambda team, p: values[p["key"]]
    moves = a.pickups()
    assert [(m["add"], m["drop"]) for m in moves] == [(fa["name"], keep_b["name"])]


def test_h2h_trades_report_both_sides_in_expected_category_wins(ranker):
    snap, _ = league(ranker, scoring="h2h")
    a = SeasonAnalyzer(ranker, snap)
    trades = a.trades()
    assert trades
    for t in trades:
        assert isinstance(t["their_points_change"], float)
        assert abs(t["their_points_change"]) <= len(a.categories)


def test_roto_trades_report_whole_points_for_the_partner(ranker):
    snap, _ = league(ranker)
    assert all(isinstance(t["their_points_change"], int) for t in SeasonAnalyzer(ranker, snap).trades())


def test_punting_a_category_lowers_the_h2h_score(ranker):
    snap, _ = league(ranker, scoring="h2h")
    assert SeasonAnalyzer(ranker, snap, punts=["TO"])._my_points() < SeasonAnalyzer(ranker, snap)._my_points()


# ---------- injuries in the totals ----------
def test_an_out_player_counts_at_reduced_value(ranker):
    healthy, rosters = league(ranker)
    star = rosters[0][0]
    hurt, _ = league(ranker, injuries={star: "out"})
    full = SeasonAnalyzer(ranker, healthy).totals[0]
    reduced = SeasonAnalyzer(ranker, hurt).totals[0]
    assert reduced[STATS_PTS] < full[STATS_PTS]
    assert SeasonAnalyzer(ranker, hurt).totals[1] == SeasonAnalyzer(ranker, healthy).totals[1]


STATS_PTS = 5  # index of PTS in analyzer.STATS


def test_injury_names_match_across_spellings(ranker):
    _, rosters = league(ranker)
    snap, _ = league(ranker, injuries={rosters[0][0].upper(): "out"})
    assert SeasonAnalyzer(ranker, snap)._injury(rosters[0][0]) == "out"


# ---------- lineup eligibility ----------
def test_a_move_may_not_leave_a_position_slot_empty(ranker):
    snap, rosters = league(ranker, slots={"C": 1, "PG": 1})
    a = SeasonAnalyzer(ranker, snap)
    center, guard = a.players[0][0], a.players[0][1]
    free_guard = ranker.find("Guard Ba")  # not on any roster
    free_center = ranker.find("Big Ah")
    assert not a._keeps_lineup([center], [free_guard])
    assert a._keeps_lineup([center], [free_center])
    assert a._keeps_lineup([guard], [free_guard])


def test_unknown_slots_do_not_restrict_moves(ranker):
    snap, _ = league(ranker)
    a = SeasonAnalyzer(ranker, snap)
    assert a._keeps_lineup(a.players[0][:1], [ranker.find("Guard Ba")])
    assert any("slots are unknown" in w for w in a.report()["warnings"])


def test_pickups_never_drop_the_only_center_for_a_guard(ranker):
    snap, rosters = league(ranker, slots={"C": 1, "PG": 1})
    for move in SeasonAnalyzer(ranker, snap).pickups():
        if move["drop"] == rosters[0][0]:
            assert ranker.find(move["add"])["pos"] == "C"


# ---------- snapshot: scoring type, warnings, injuries ----------
def test_scoring_type_wording():
    assert [snapshots.scoring_from_text(t) for t in ("head", "H2H_CATEGORY", "roto", "ROTO", "headpoint",
                                                     "TOTAL_POINTS", None)] == [
        "h2h", "h2h", "roto", "roto", "points", "points", "roto"]


def test_unsupported_categories_are_named():
    cats = [{"display_name": "PTS"}, {"display_name": "DD"}, {"display_name": "A/T"}, {"display_name": "3PM"}]
    assert unsupported_categories(cats) == ["DD", "A/T"]


class FakeYahooLeague:
    def settings(self):
        return {"name": "Y", "scoring_type": "head"}

    def teams(self):
        return {"t.1": {"name": "A", "is_owned_by_current_login": "1"}, "t.2": {"name": "B"}}

    def to_team(self, key):
        return NS(roster=lambda: [{"name": f"P{key}", "status": "INJ" if key == "t.2" else ""}])

    def free_agents(self, pos):
        return [{"name": "FA", "status": "GTD"}]

    def stat_categories(self):
        return [{"display_name": "PTS"}, {"display_name": "DD"}]

    def positions(self):
        return {"PG": {"count": 1}, "Util": {"count": 2}, "BN": {"count": 3}}

    def team_key(self):
        return "t.1"

    def current_week(self):
        raise RuntimeError("offseason")


def test_yahoo_snapshot_reads_scoring_slots_and_warns_about_unsupported_stats():
    snap = snapshots.from_yahoo(FakeYahooLeague(), "yahoo-test-1", user="u")
    assert snap.scoring == "h2h" and snap.slots == {"PG": 1, "Util": 2}
    assert snap.injuries == {"Pt.2": "out", "FA": "questionable"}
    assert snap.warnings == ["These scored stats aren't analyzed: DD."]


def espn_settings_request(slot_counts):
    """espn_api's basketball settings drop rosterSettings, so the slots come from a raw request."""
    def league_get(params=None, headers=None, extend=""):
        assert params == {"view": "mSettings"}
        return {"settings": {"rosterSettings": {"lineupSlotCounts": slot_counts}}}
    return league_get


def test_espn_snapshot_reads_unsupported_stats_and_slots():
    league = rich_league()
    league.settings.scoring_type = "H2H_CATEGORY"
    # ESPN slot ids: 0 PG, 4 C, 8 G/F, 11 UT (flex), 12 bench, 13 IR
    league.espn_request.league_get = espn_settings_request({"0": 1, "4": 1, "8": 1, "11": 2, "12": 3, "13": 1})
    snap = snapshots.from_espn(league, "9100", swid=SWID, user="u9")
    assert snap.scoring == "h2h" and snap.slots == {"PG": 1, "C": 1, "Util": 3}  # G/F has no match: a flex
    assert snap.warnings == ["These scored stats aren't analyzed: stat 99."]


def test_espn_slots_are_empty_when_the_request_fails():
    league = rich_league()

    def broken(params=None, headers=None, extend=""):
        raise RuntimeError("ESPN is down")

    league.espn_request.league_get = broken
    assert espn_league_info.starting_slots(league) == {}


def test_points_leagues_are_flagged():
    snap, _ = snapshots.LeagueSnapshot("t", "L", ["PTS"], ["a"], 0, [[]], scoring="points"), None
    snap.warnings = snapshots._scoring_warnings("points", [])
    assert "points league" in snap.warnings[0]


def test_outside_injuries_never_override_the_platform():
    snap = snapshots.LeagueSnapshot("t", "L", [], [], 0, [], injuries={"Jaylen Brown": "questionable"})
    merged = snap.with_injuries({"jaylen brown": "out", "Luka Doncic": "out"})
    assert merged.injuries == {"Jaylen Brown": "questionable", "Luka Doncic": "out"}
    assert snap.injuries == {"Jaylen Brown": "questionable"}  # the original (maybe cached) is untouched


# ---------- schedule ----------
def test_games_remaining_and_rest_of_week():
    days = {d: [{"home_team": "LAL", "away_team": "BOS"}] for d in
            ("2026-11-02", "2026-11-04", "2026-11-08", "2026-11-09", "2026-11-20")}
    s = Schedule(days)
    assert s.last_day() == date(2026, 11, 20)
    assert s.games_remaining("LAL", date(2026, 11, 3)) == 4
    assert s.games_rest_of_week("LAL", date(2026, 11, 3)) == 2  # the 4th and the 8th (Sunday)
    assert s.games_remaining("LAL", date(2026, 12, 1)) == 0
    assert Schedule({}).last_day() is None and Schedule({}).games_remaining("LAL", TODAY) == 0


# ---------- ESPN status feeds ----------
INJURY_PAYLOAD = {"injuries": [{"displayName": "Atlanta Hawks", "injuries": [
    {"status": "Out", "shortComment": "Knee.", "date": "2026-10-09T02:30Z", "athlete": {"displayName": "A One"}},
    {"status": "Day-To-Day", "shortComment": "Ankle.", "date": "d", "athlete": {"displayName": "B Two"}},
    {"status": "Probable", "athlete": {"displayName": "C Three"}},
    {"status": "Available", "athlete": {"displayName": "D Four"}},
    {"status": "Out", "athlete": {}},
]}]}
OWNERSHIP_PAYLOAD = {"players": [
    {"player": {"fullName": "A One", "ownership": {"percentOwned": 99.93, "percentStarted": 80.1, "percentChange": -1.2}}},
    {"player": {"fullName": "No Own", "ownership": {}}},
    {"player": {"ownership": {"percentOwned": 5}}},
]}


def test_injury_wording():
    assert [espn_status.injury_level(s) for s in
            ("Out", "Injured Reserve", "Suspension", "Day-To-Day", "Questionable", "Doubtful", "Available", None)] == [
        "out", "out", "out", "questionable", "questionable", "questionable", None, None]


def test_parse_injuries_keeps_only_real_entries():
    parsed = espn_status.parse_injuries(INJURY_PAYLOAD)
    assert set(parsed) == {"A One", "B Two", "C Three"}
    assert parsed["A One"] == {"level": "out", "status": "Out", "note": "Knee.", "date": "2026-10-09T02:30Z",
                               "team": "Atlanta Hawks"}


def test_parse_ownership():
    assert espn_status.parse_ownership(OWNERSHIP_PAYLOAD) == {
        "A One": {"percent_owned": 99.9, "percent_started": 80.1, "change": -1.2}}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_source_sends_the_fantasy_filter_and_season():
    seen = []

    def get(url, headers=None, params=None, timeout=None):
        seen.append((url, headers, params))
        return FakeResponse(OWNERSHIP_PAYLOAD if "fantasy" in url else INJURY_PAYLOAD)

    source = espn_status.EspnStatusSource(get=get, limiter=NS(wait=lambda: None), sleep=lambda s: None)
    assert "A One" in source.injuries() and "A One" in source.ownership(2027, limit=5)
    url, headers, params = seen[1]
    assert "/seasons/2027/" in url and params == {"view": "kona_player_info"}
    assert json.loads(headers["X-Fantasy-Filter"])["players"]["limit"] == 5


class FakeStatusSource:
    def __init__(self, injuries=None, ownership=None):
        self._i, self._o = injuries, ownership

    def injuries(self):
        if self._i is None:
            raise RuntimeError("down")
        return self._i

    def ownership(self, year):
        if self._o is None:
            raise RuntimeError("down")
        return self._o


def test_status_job_stores_each_feed(tmp_path):
    store = LocalDatasetStore(tmp_path)
    result = status_job.run(store, FakeStatusSource({"A One": {"level": "out"}}, {"A One": {"percent_owned": 90}}))
    assert result == {"injuries": 1, "ownership": 1}
    assert store.get("injuries")["players"] == {"A One": {"level": "out"}} and store.get("injuries")["as_of"]
    assert store.get("ownership")["players"]["A One"]["percent_owned"] == 90


def test_status_job_survives_one_feed_failing_but_not_both(tmp_path):
    store = LocalDatasetStore(tmp_path)
    assert status_job.run(store, FakeStatusSource(None, {"A": {"percent_owned": 1}})) == {"injuries": None, "ownership": 1}
    assert store.get("injuries") is None
    with pytest.raises(RuntimeError):
        status_job.run(store, FakeStatusSource(None, None))


def test_the_job_is_runnable_from_the_command_line():
    from appl.ingest.__main__ import JOBS

    assert "player_status" in JOBS


# ---------- PlayerData ----------
STATS = {
    "Riser Man": {"season": {"Minutes": 20.0},
                  "last_14_days": {"Games Played": 5, "Average Minutes": 29.5, "Points": 15.0},
                  "last_7_days": {"Games Played": 3, "Average Minutes": 31.0, "Points": 17.0}, "last_30_days": None},
    "Faller Man": {"season": {"Minutes": 30.0}, "last_14_days": {"Games Played": 6, "Average Minutes": 24.0}},
    "Few Games": {"season": {"Minutes": 10.0}, "last_14_days": {"Games Played": 1, "Average Minutes": 40.0}},
    "No Window": {"season": {"Minutes": 10.0}, "last_14_days": None},
}


@pytest.fixture
def data():
    return PlayerData({"A One": {"level": "out", "status": "Out", "note": "Knee.", "date": "d"}},
                      {"A One": {"percent_owned": 99.9}}, STATS, "t1", "t2")


def test_form_has_short_keys_and_a_minutes_trend(data):
    form = data.form("riser man")
    assert form["last_14_days"] == {"games": 5, "min": 29.5, "pts": 15.0}
    assert form["minutes_trend"] == 9.5
    assert "last_30_days" not in form


def test_minutes_trend_needs_enough_games(data):
    assert data.form("Few Games")["minutes_trend"] is None
    assert data.form("No Window") is None and data.form("Nobody") is None


def test_risers_are_ranked_by_extra_minutes_and_exclude_fallers(data):
    risers = data.risers(["Faller Man", "Riser Man", "Few Games", "Nobody"])
    assert [r["name"] for r in risers] == ["Riser Man"]


def test_injury_and_ownership_lookups_ignore_case_and_accents(data):
    assert data.injury("a one")["note"] == "Knee." and data.injury("Nobody") is None
    assert data.ownership("A ONE")["percent_owned"] == 99.9
    assert data.injury_levels() == {"a one": "out"}


def test_loader_reads_the_datasets_and_caches(tmp_path):
    player_status.clear_cache()
    store = LocalDatasetStore(tmp_path)
    store.put("injuries", {"as_of": "now", "players": {"A One": {"level": "out"}}})
    clock = [0.0]
    first = player_status.load(store, now=lambda: clock[0], today=date(2026, 11, 1))
    assert first.injuries_as_of == "now" and first.injury("A One")["level"] == "out"
    store.put("injuries", {"as_of": "later", "players": {}})
    assert player_status.load(store, now=lambda: clock[0]) is first  # cached
    clock[0] = player_status.CACHE_SECONDS + 1
    assert player_status.load(store, now=lambda: clock[0]).injuries_as_of == "later"
    player_status.clear_cache()


def test_loader_without_datasets_gives_empty_data(tmp_path):
    player_status.clear_cache()
    empty = player_status.load(LocalDatasetStore(tmp_path))
    assert empty.form("x") is None and empty.injury_levels() == {}
    player_status.clear_cache()


# ---------- the toolkit with the extra data ----------
@pytest.fixture
def toolkit(ranker, data):
    snap, rosters = league(ranker, scoring="h2h")
    return Toolkit(ranker, snap, schedule=None, today=TODAY, data=data), rosters


def result(kit, tool, **args):
    return json.loads(kit.call(tool, args))


def test_overview_names_the_scoring_format_and_data_age(toolkit):
    kit, _ = toolkit
    out = result(kit, "get_team_overview")
    assert out["scoring"] == "h2h" and "expected categories" in out["score_unit"]
    assert out["data_notes"] == {"injury_report_as_of": "t1", "ownership_as_of": "t2", "schedule_loaded": False}
    assert any("slots are unknown" in w for w in out["warnings"])


def test_lookup_player_includes_form_ownership_and_schedule():
    ranker = DraftRanker([{**p, "team": "LAL"} for p in pool_with_positions()], num_teams=4, roster_size=3)
    days = {d: [{"home_team": "LAL", "away_team": "BOS"}] for d in ("2026-11-02", "2026-11-04", "2026-11-09")}
    snap, rosters = league(ranker)
    stats = {rosters[0][0]: {"season": {"Minutes": 20.0},
                             "last_14_days": {"Games Played": 4, "Average Minutes": 26.0}}}
    data = PlayerData({rosters[0][0]: {"level": "questionable", "note": "Ankle."}},
                      {rosters[0][0]: {"percent_owned": 77.0}}, stats)
    out = result(Toolkit(ranker, snap, Schedule(days), TODAY, data), "lookup_player", name=rosters[0][0])
    assert out["injury"]["note"] == "Ankle." and out["percent_owned"] == 77.0
    assert out["recent_form"]["minutes_trend"] == 6.0
    assert (out["games_next_7_days"], out["games_rest_of_this_week"], out["games_rest_of_season"]) == (2, 2, 3)


def test_find_risers_looks_at_free_agents_only(ranker):
    snap, rosters = league(ranker)
    free = SeasonAnalyzer(ranker, snap)._free_agents(limit=60)[0]["name"]
    stats = {free: {"season": {"Minutes": 15.0}, "last_14_days": {"Games Played": 5, "Average Minutes": 25.0}},
             rosters[0][0]: {"season": {"Minutes": 15.0}, "last_14_days": {"Games Played": 5, "Average Minutes": 35.0}}}
    out = result(Toolkit(ranker, snap, None, TODAY, PlayerData(stats=stats)), "find_risers")
    assert [r["name"] for r in out["risers"]] == [free]


def test_find_risers_explains_when_there_is_no_data(ranker):
    snap, _ = league(ranker)
    assert "note" in result(Toolkit(ranker, snap, None, TODAY), "find_risers")


def test_pickups_carry_ownership_and_injury_notes(ranker):
    snap, _ = league(ranker)
    pickups = SeasonAnalyzer(ranker, snap).pickups()
    assert pickups
    name = pickups[0]["add"]
    data = PlayerData({name: {"level": "questionable", "note": "Sore knee."}}, {name: {"percent_owned": 12.5}})
    out = result(Toolkit(ranker, snap, None, TODAY, data), "suggest_pickups")["pickups"]
    row = next(r for r in out if r["add"] == name)
    assert row["percent_owned"] == 12.5 and row["injury_note"] == "Sore knee."


# ---------- the factory: every league type ----------
def build(factory, **request):
    return factory({"user_id": USER, **request})


def test_manual_league_toolkit_uses_the_injury_report(tmp_path, monkeypatch, ranker):
    monkeypatch.setattr("appl.ai.tools.ranker_for", lambda snap: ranker)  # the real one fetches stats
    store = ManualLeagueStore(tmp_path)
    created = _drafted_league(store)
    snap_names = [n for r in __import__("appl.draft.manual_league", fromlist=["x"]).current_rosters(created) for n in r]
    data = PlayerData({snap_names[0]: {"level": "out"}})
    factory = league_toolkit_factory(store, load_data=lambda: data)
    kit = build(factory, league_id=f"manual-{created['id']}")
    assert kit.snapshot.injuries.get(snap_names[0].lower()) == "out"
    assert build(factory, league_id=f"manual-{created['id']}", user_id="someone-else") is None


def test_espn_league_toolkit(monkeypatch, ranker):
    league_obj = rich_league()
    service = NS(load_league=lambda user, league_id: (league_obj, SWID))
    seen = {}
    monkeypatch.setattr("appl.ai.tools.ranker_for", lambda snap: seen.setdefault("snap", snap) and ranker)
    kit = build(league_toolkit_factory(espn_service=service, load_data=PlayerData.empty), league_id="espn-9200")
    assert kit.snapshot.key == "espn:9200" and kit.snapshot.my_team == 0
    assert seen["snap"].injuries == {"Hurt": "out", "B": "questionable"}


def test_yahoo_league_toolkit(monkeypatch, ranker):
    calls = []

    def fake_yahoo(league_id, user_id):
        calls.append((league_id, user_id))
        return snapshots.from_yahoo(FakeYahooLeague(), league_id, user=user_id)

    monkeypatch.setattr("appl.ai.tools.ranker_for", lambda snap: ranker)
    kit = build(league_toolkit_factory(yahoo_snapshot=fake_yahoo, load_data=PlayerData.empty), league_id="466.l.77")
    assert calls == [("466.l.77", USER)] and kit.snapshot.name == "Y"


def test_the_injury_report_never_changes_a_platform_league(monkeypatch, ranker):
    cached = snapshots.from_yahoo(FakeYahooLeague(), "466.l.78", user=USER)
    before = dict(cached.injuries)
    data = PlayerData({"Healthy Guy": {"level": "out"}, "Pt.2": {"level": "questionable"}})
    monkeypatch.setattr("appl.ai.tools.ranker_for", lambda snap: ranker)
    kit = build(league_toolkit_factory(yahoo_snapshot=lambda *a: cached, load_data=lambda: data),
                league_id="466.l.78")
    # Yahoo lists every injured player, so one it leaves out is healthy, whatever the report says
    assert kit.snapshot.injuries == before and cached.injuries == before


def test_factory_returns_none_instead_of_failing(ranker):
    def broken(league_id, user_id):
        raise RuntimeError("Yahoo is down")

    factory = league_toolkit_factory(yahoo_snapshot=broken, load_data=PlayerData.empty)
    assert build(factory, league_id="466.l.77") is None  # platform error: chat answers without tools
    assert factory({"league_id": "466.l.77"}) is None  # no signed-in user
    assert factory({"user_id": USER}) is None  # no league
    assert build(league_toolkit_factory(yahoo_snapshot=lambda *a: None, load_data=PlayerData.empty),
                 league_id="466.l.77") is None  # Yahoo not connected
    assert build(league_toolkit_factory(load_data=PlayerData.empty), league_id="espn-1") is None  # no ESPN service
