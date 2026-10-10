import logging
from types import SimpleNamespace as NS

import pytest
from flask import Flask

from appl.ai.access import CurrentUser, SessionAccess
from appl.fantasy_integrations.espn import espn_credentials, espn_service
from appl.fantasy_integrations.espn.espn_service import (
    EspnError, EspnService, espn_chat_id, espn_id_from_chat, espn_year)
from appl.fantasy_integrations.espn.sync_league.sync_espn_league import EspnLeague
from appl.repository.firestore.espn_data import EspnLeagueRepository
from appl.router.espn_routes import EspnRouter

S2, SWID = "AEB-secret-cookie-value", "{ABC-123-SWID}"


@pytest.fixture
def key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("ESPN_COOKIE_KEY", Fernet.generate_key().decode())


# ---------- fakes ----------
def player(name, injury="ACTIVE"):
    return NS(name=name, position="PG", proTeam="LAL", injuryStatus=injury, stats={"avg": {"PTS": 20.0}})


def team(name, tid, owners=(), players=()):
    return NS(team_name=name, team_id=tid, owners=list(owners), wins=3, losses=1, ties=0, roster=list(players))


class FakeLeague:
    def __init__(self, fail=()):
        self.year = 2026
        self.settings = NS(name="Hoops", team_count=2, reg_season_count=20, playoff_team_count=4)
        self.currentMatchupPeriod = 2
        self.fail = set(fail)
        mine = team("Mine", 1, owners=[{"id": SWID}], players=[player("A")])
        other = team("Other", 2, players=[player("B", "OUT")])
        self.teams = [mine, other]

    def standings(self):
        if "standings" in self.fail:
            raise RuntimeError("boom")
        return self.teams

    def scoreboard(self, week):
        if "matchups" in self.fail:
            raise RuntimeError("boom")
        a, b = self.teams
        return [NS(home_team=a, away_team=b, home_final_score=5, away_final_score=4, winner="HOME")]

    def free_agents(self, size=50):
        return [player("FA")]


class FakeBlob:
    def __init__(self, ok=True):
        self.ok, self.uploads = ok, {}

    def upload_json_with_retries(self, data, path):
        self.uploads[path] = data
        return self.ok


class FakeIndexer:
    def __init__(self):
        self.calls = []

    def update_league_files(self, league_id, files):
        self.calls.append((league_id, files))


class FakeAuthRepo:
    def __init__(self):
        self.rows = {}

    def get_by_user_id(self, uid):
        return self.rows.get(uid)

    def save(self, uid, s2_enc, swid_enc):
        self.rows[uid] = {"espn_s2_enc": s2_enc, "swid_enc": swid_enc}

    def delete_by_user_id(self, uid):
        self.rows.pop(uid, None)


class FakeLeagueRepo:
    def __init__(self):
        self.rows = {}

    def league_exist_for_user(self, league_id, uid):
        return self.rows.get((uid, league_id))

    def save(self, uid, league_id, data):
        self.rows.setdefault((uid, league_id), {}).update(data, user_id=uid, league_id=league_id)

    def get_by_user_id(self, uid):
        return [r for (u, _), r in self.rows.items() if u == uid]

    def delete_by_user_id(self, uid):
        self.rows = {k: v for k, v in self.rows.items() if k[0] != uid}


def make_service(league=None, opened=None):
    def open_league(league_id, year, s2, swid):
        if opened is not None:
            opened.append((league_id, year, s2, swid))
        return league or FakeLeague()

    return EspnService(FakeIndexer(), FakeLeagueRepo(), FakeAuthRepo(), open_league)


# ---------- ids ----------
def test_chat_ids_round_trip_and_do_not_collide_with_yahoo():
    assert espn_chat_id("123") == "espn-123"
    assert espn_id_from_chat("espn-123") == "123"
    assert espn_id_from_chat("123") is None and espn_id_from_chat("manual-9") is None
    assert espn_year("2025-26") == 2026


# ---------- credentials ----------
def test_cookies_round_trip_and_are_not_plaintext(key):
    token = espn_credentials.encrypt(S2)
    assert S2 not in token and espn_credentials.decrypt(token) == S2


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("ESPN_COOKIE_KEY", raising=False)
    with pytest.raises(espn_credentials.CredentialsError):
        espn_credentials.encrypt(S2)


def test_rotated_key_asks_to_reconnect(monkeypatch, key):
    from cryptography.fernet import Fernet
    token = espn_credentials.encrypt(S2)
    monkeypatch.setenv("ESPN_COOKIE_KEY", Fernet.generate_key().decode())
    with pytest.raises(espn_credentials.CredentialsError, match="reconnect"):
        espn_credentials.decrypt(token)


# ---------- EspnLeague ----------
def test_sync_produces_the_same_parts_as_yahoo():
    blob = FakeBlob()
    espn = EspnLeague(FakeLeague(), "espn-1", sleep=lambda s: None)
    results = espn.sync_full_league(blob)
    assert set(results) == {"league_settings", "standings", "matchups", "free_agents", "team_rosters"}
    assert "espn-1/standings.json" in blob.uploads and espn.critical_ok
    assert results["matchups"][0][0]["team_win_name"] == "Mine"
    assert results["team_rosters"]["Other"][0]["injury_status"] == "OUT"


def test_a_failed_part_is_listed_and_the_others_still_sync():
    espn = EspnLeague(FakeLeague(fail={"matchups"}), "espn-1", sleep=lambda s: None)
    results = espn.sync_full_league(FakeBlob())
    assert espn.failed == ["matchups"] and "matchups" not in results and espn.critical_ok


def test_a_failed_critical_part_is_not_fresh():
    espn = EspnLeague(FakeLeague(fail={"standings"}), "espn-1", sleep=lambda s: None)
    espn.sync_full_league(FakeBlob())
    assert not espn.critical_ok


# ---------- EspnService ----------
def test_connect_stores_cookies_encrypted_and_finds_my_team(key):
    svc = make_service()
    out = svc.connect("u1", "555", 2026, S2, SWID)
    assert out == {"league_id": "555", "league_name": "Hoops"}
    stored = svc.auth_repo.rows["u1"]
    assert S2 not in stored.values() and SWID not in stored.values()
    assert svc.league_repo.rows[("u1", "555")]["team_name"] == "Mine"


def test_public_league_needs_no_cookies_or_key(monkeypatch):
    monkeypatch.delenv("ESPN_COOKIE_KEY", raising=False)
    svc = make_service()
    svc.connect("u1", "555", 2026)
    assert "u1" not in svc.auth_repo.rows


def test_connect_rejects_bad_input(key):
    svc = make_service()
    with pytest.raises(EspnError):
        svc.connect("u1", "abc", 2026)
    with pytest.raises(EspnError, match="both cookies"):
        svc.connect("u1", "555", 2026, S2, None)


def test_connect_with_cookies_but_no_key_stores_nothing(monkeypatch):
    monkeypatch.delenv("ESPN_COOKIE_KEY", raising=False)
    svc = make_service()
    with pytest.raises(espn_credentials.CredentialsError):
        svc.connect("u1", "555", 2026, S2, SWID)
    assert not svc.auth_repo.rows and not svc.league_repo.rows


def test_access_denied_becomes_a_friendly_error(key):
    class ESPNAccessDenied(Exception):
        pass

    def deny(*a):
        raise ESPNAccessDenied("401 with s2=" + S2)

    svc = EspnService(FakeIndexer(), FakeLeagueRepo(), FakeAuthRepo(), deny)
    with pytest.raises(EspnError) as e:
        svc.connect("u1", "555", 2026, S2, SWID)
    assert S2 not in str(e.value) and "cookies" in str(e.value)


def test_sync_uses_the_users_decrypted_cookies_indexes_and_marks_fresh(key, monkeypatch):
    opened = []
    svc = make_service(opened=opened)
    svc.connect("u1", "601", 2026, S2, SWID)
    opened.clear()
    monkeypatch.setattr(espn_service, "build_blob_storage", lambda c: FakeBlob())
    result = svc.sync_league_data("u1", "601")
    assert result["success"] and opened == [(601, 2026, S2, SWID)]
    chat_id, files = svc.document_indexer.calls[0]
    assert chat_id == "espn-601" and "standings" in files
    assert svc.league_repo.rows[("u1", "601")]["last_blob_sync"]
    # fresh now: the second visit doesn't sync again
    assert svc.sync_league_data("u1", "601")["skipped"] is True


def test_partial_sync_with_a_failed_critical_part_is_not_marked_fresh(key, monkeypatch):
    svc = make_service(FakeLeague(fail={"standings"}))
    svc.connect("u1", "602", 2026)
    monkeypatch.setattr(espn_service, "build_blob_storage", lambda c: FakeBlob())
    monkeypatch.setattr("appl.ingest.http.time.sleep", lambda s: None, raising=False)
    result = svc.sync_league_data("u1", "602")
    assert not result["success"] and "last_blob_sync" not in svc.league_repo.rows[("u1", "602")]


def test_cannot_sync_someone_elses_league(key):
    svc = make_service()
    svc.connect("u1", "603", 2026)
    assert svc.sync_league_data("u2", "603")["success"] is False


def test_disconnect_forgets_cookies_and_leagues(key):
    svc = make_service()
    svc.connect("u1", "604", 2026, S2, SWID)
    svc.disconnect("u1")
    assert not svc.auth_repo.rows and not svc.league_repo.rows


# ---------- access ----------
def test_espn_league_access_is_per_user():
    repo = FakeLeagueRepo()
    repo.save("u1", "700", {})
    sa = SessionAccess(lambda: pytest.fail("not a Yahoo league"), None, lambda: repo)
    assert sa.can_access_league(CurrentUser("u1"), "espn-700") is True
    assert sa.can_access_league(CurrentUser("u2"), "espn-700") is False
    assert sa.can_access_league(CurrentUser("u1"), "espn-701") is False


def test_espn_chat_id_never_falls_through_to_yahoo_or_without_a_repo():
    yahoo_checked = []

    class YahooRepo:
        def league_exist_for_user(self, *a):
            yahoo_checked.append(a)
            return True

    assert SessionAccess(YahooRepo).can_access_league(CurrentUser("u1", "y1"), "espn-700") is False
    assert not yahoo_checked


def test_repository_rejects_non_numeric_league_ids_without_touching_storage():
    repo = EspnLeagueRepository(client=object())
    assert repo.league_exist_for_user("../x", "u1") is None
    assert repo.league_exist_for_user("espn-1", "u1") is None


# ---------- routes ----------
class FakeRouteService:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def connect(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return {"league_id": args[1], "league_name": "Hoops"}

    def disconnect(self, uid):
        self.calls.append(("disconnect", uid))


def route_client(service):
    from flask import Blueprint, render_template_string
    from pathlib import Path
    static = str(Path(__file__).resolve().parents[2] / "static")
    app = Flask(__name__, template_folder=static)
    app.secret_key = "t"
    auth = Blueprint("auth", __name__)
    main = Blueprint("main", __name__)
    main.add_url_rule("/", "homepage", lambda: "home")  # where login is required
    main.add_url_rule("/dashboard", "dashboard", lambda: "dash")
    main.add_url_rule("/ai-chat/espn/<league_id>", "ai_chat_espn", lambda league_id: "chat")
    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(EspnRouter(None, service).get_bp())
    return app.test_client()


def test_connect_requires_login():
    r = route_client(FakeRouteService()).post("/espn/connect", data={"league_id": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_connect_redirects_to_the_chat_and_passes_the_form():
    svc = FakeRouteService()
    c = route_client(svc)
    with c.session_transaction() as s:
        s["user_id"] = "u1"
    r = c.post("/espn/connect", data={"league_id": "55", "season_year": "2026", "espn_s2": S2, "swid": SWID})
    assert r.status_code == 302 and r.headers["Location"].endswith("/ai-chat/espn/55")
    assert svc.calls == [("u1", "55", 2026, S2, SWID)]


def test_connect_errors_never_echo_the_cookies(caplog):
    svc = FakeRouteService(EspnError("ESPN refused access."))
    c = route_client(svc)
    with c.session_transaction() as s:
        s["user_id"] = "u1"
    with caplog.at_level(logging.DEBUG):
        r = c.post("/espn/connect", data={"league_id": "55", "espn_s2": S2, "swid": SWID})
    assert r.status_code == 400 and "refused" in r.get_data(as_text=True)
    assert S2 not in r.get_data(as_text=True) and S2 not in caplog.text


def test_missing_encryption_key_is_a_503_not_a_leak():
    svc = FakeRouteService(espn_credentials.CredentialsError("ESPN_COOKIE_KEY is not set"))
    c = route_client(svc)
    with c.session_transaction() as s:
        s["user_id"] = "u1"
    r = c.post("/espn/connect", data={"league_id": "55", "espn_s2": S2, "swid": SWID})
    assert r.status_code == 503 and "ESPN_COOKIE_KEY" not in r.get_data(as_text=True)


# ---------- phase 2: snapshot, draft tracker, ownership on the pages ----------
from appl.draft.espn_draft import EspnDraftTracker  # noqa: E402
from appl.fantasy_integrations.espn import espn_league_info  # noqa: E402
from appl.season import snapshot as snapshots  # noqa: E402


def rich_league(draft=None, injuries=()):
    league = FakeLeague()
    league.settings._raw_scoring_settings = {"scoringItems": [
        {"statId": 19}, {"statId": 20}, {"statId": 17}, {"statId": 0}, {"statId": 6}, {"statId": 3},
        {"statId": 2}, {"statId": 1}, {"statId": 11}, {"statId": 99}]}
    league.teams[0].roster = [player("A"), player("Hurt", "OUT")]
    league.teams[1].roster = [player("B", "DAY_TO_DAY")]
    league.player_map = {11: "Alpha", 12: "Bravo", 13: "Charlie"}
    league.espn_request = NS(get_league_draft=lambda: draft or {})
    return league


def test_categories_come_from_the_scoring_items():
    assert espn_league_info.categories(rich_league()) == [
        "FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"]
    assert espn_league_info.categories(FakeLeague()) == [
        "FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"]  # default nine


def test_injury_levels():
    assert [espn_league_info.injury_level(s) for s in ("OUT", "INJURY_RESERVE", "DAY_TO_DAY", "ACTIVE", None)] == [
        "out", "out", "questionable", None, None]


def test_espn_snapshot_finds_my_team_opponent_and_injuries():
    snap = snapshots.from_espn(rich_league(), "9001", swid=SWID, user="u1")
    assert snap.key == "espn:9001" and snap.name == "Hoops"
    assert snap.team_names == ["Mine", "Other"] and snap.my_team == 0
    assert snap.rosters == [["A", "Hurt"], ["B"]]
    assert snap.opponent == 1
    assert snap.injuries == {"Hurt": "out", "B": "questionable"}
    assert snap.num_teams == 2


def test_espn_snapshot_without_cookies_has_no_opponent():
    snap = snapshots.from_espn(rich_league(), "9002", swid=None, user="u1")
    assert snap.my_team == 0 and snap.opponent is None


def test_espn_snapshot_is_cached_per_user():
    league = rich_league()
    a = snapshots.from_espn(league, "9003", swid=SWID, user="u1")
    assert snapshots.from_espn(league, "9003", swid=SWID, user="u1") is a
    assert snapshots.from_espn(league, "9003", swid=None, user="u2") is not a


def pick(n, team, pid, bid=0, rnd=1):
    return {"overallPickNumber": n, "roundId": rnd, "teamId": team, "playerId": pid, "bidAmount": bid}


def test_snake_draft_state_reads_live_picks_before_espn_marks_it_done():
    draft = {"draftDetail": {"drafted": False, "inProgress": True,
                             "picks": [pick(2, 2, 12), pick(1, 1, 11)]},
             "settings": {"draftSettings": {"type": "SNAKE", "pickOrder": [1, 2]}}}
    tracker = EspnDraftTracker(rich_league(draft), "9004", swid=SWID, user="u1")
    state = tracker.state()
    assert state["draft_status"] == "draft" and not state["is_auction"]
    assert [p["player_name"] for p in state["picks"]] == ["Alpha", "Bravo"]
    assert state["my_roster"] == ["Alpha"] and state["taken_names"] == ["Alpha", "Bravo"]
    assert state["my_next_pick"] == 4 and state["picks_until_my_turn"] == 1
    assert tracker.league_info()["my_draft_position"] == 1


def test_snake_draft_asks_for_a_position_when_espn_has_no_order():
    draft = {"draftDetail": {"picks": []}}
    state = EspnDraftTracker(rich_league(draft), "9005", swid=SWID).state()
    assert state["draft_status"] == "predraft" and state["needs_draft_position"] is True
    assert EspnDraftTracker(rich_league(draft), "9005", swid=SWID).state(2)["my_next_pick"] == 2


def test_auction_state_tracks_budgets_and_max_bid():
    draft = {"draftDetail": {"inProgress": True, "picks": [pick(1, 1, 11, bid=60), pick(2, 2, 12, bid=40)]},
             "settings": {"draftSettings": {"type": "AUCTION", "auctionBudget": 200}}}
    state = EspnDraftTracker(rich_league(draft), "9006", swid=SWID).state()
    assert state["is_auction"] and state["my_budget_left"] == 140
    mine = next(t for t in state["teams"] if t["is_mine"])
    assert mine["spots_left"] == 1 and mine["max_bid"] == 139  # roster_size 2 from the fake rosters
    assert state["league_budget_total"] == 400 and state["league_budget_left"] == 300


def test_auction_is_inferred_from_bids_when_settings_are_missing():
    draft = {"draftDetail": {"picks": [pick(1, 1, 11, bid=5)]}}
    assert EspnDraftTracker(rich_league(draft), "9007", swid=SWID).league_info()["is_auction"]


def test_tracker_plugs_into_the_draft_ranker_inputs():
    from appl.draft.ranker import categories_from_yahoo
    info = EspnDraftTracker(rich_league({}), "9008", swid=SWID).league_info()
    assert categories_from_yahoo(info["stat_categories"])[:2] == ["FG%", "FT%"]
    assert EspnDraftTracker(rich_league({}), "9008").yahoo_ranks() == {}


def test_load_league_is_ownership_checked_and_cached(key):
    opened = []
    svc = make_service(opened=opened)
    svc.connect("u1", "801", 2026, S2, SWID)
    opened.clear()
    with pytest.raises(KeyError):
        svc.load_league("u2", "801")
    clock = [0.0]
    a, swid = svc.load_league("u1", "801", now=lambda: clock[0])
    b, _ = svc.load_league("u1", "801", now=lambda: clock[0] + 10)
    assert a is b and swid == SWID and len(opened) == 1
    svc.load_league("u1", "801", now=lambda: clock[0] + 500)
    assert len(opened) == 2


def test_draft_and_season_pages_hide_other_users_leagues(key):
    from flask import Blueprint
    from appl.router.draft_routes import DraftRouter
    from appl.router.season_routes import SeasonRouter
    from pathlib import Path
    static = str(Path(__file__).resolve().parents[2] / "static")
    svc = make_service()
    svc.connect("u1", "802", 2026, S2, SWID)
    app = Flask(__name__, template_folder=static)
    app.secret_key = "t"
    home = Blueprint("main", __name__)
    home.add_url_rule("/", "homepage", lambda: "home")
    app.register_blueprint(home)
    app.register_blueprint(DraftRouter(store=object(), tokens=object(), espn=svc).get_bp())
    app.register_blueprint(SeasonRouter(store=object(), briefs=object(), schedule=object(), espn=svc).get_bp())
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u2"
    assert c.get("/draft/espn/802").status_code == 302
    assert c.get("/season/espn/802").status_code == 302
    assert c.get("/draft/espn/802/state").status_code == 404
    assert c.get("/draft/espn/802/players").status_code == 404
    assert c.get("/season/espn/802/report").status_code == 404
    assert c.post("/season/espn/802/brief").status_code == 404
