import importlib
from pathlib import Path

import pytest
from flask import Flask

from appl.draft import jev_chooser, player_pool
from appl.draft.manual_league import ManualLeagueError, ManualLeagueStore, current_rosters
from appl.draft.ranker import DraftRanker
from appl.season import jev_advisor, report_writer, service, snapshot as snapshots
from appl.season.analyzer import SeasonAnalyzer
from appl.tests.unit.conftest import FakeLLMClient
from appl.tests.unit.test_draft import _name, _player

USER = "user-1"
POOL = [_player(_name("Big", i), True, i) for i in range(80)] + [
    _player(_name("Guard", i), False, 100 + i) for i in range(120)
]


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setattr(jev_chooser, "_cache", {})
    monkeypatch.setattr(jev_chooser, "_failed_until", 0.0)


@pytest.fixture
def store(tmp_path):
    return ManualLeagueStore(tmp_path)


def _drafted_league(store, teams=4, size=3):
    league = store.create(USER, {"name": "Friends", "num_teams": teams, "roster_size": size, "my_slot": 1})
    names = [p["name"] for p in POOL]
    for name in names[: teams * size]:
        store.add_pick(USER, league["id"], name)
    return store.get(USER, league["id"])


def _snapshot_league(teams=12, size=13, me=3):
    """A snake draft of the best players, so rosters are realistic."""
    ranker = DraftRanker(POOL, num_teams=teams, roster_size=size)
    names = [p["name"] for p in sorted(ranker.players, key=lambda p: -sum(p["z"].values()))]
    rosters = [[] for _ in range(teams)]
    for i, name in enumerate(names[: teams * size]):
        rnd, pos = divmod(i, teams)
        rosters[pos if rnd % 2 == 0 else teams - 1 - pos].append(name)
    snap = snapshots.LeagueSnapshot("test", "L", ranker.categories, [f"T{i}" for i in range(teams)], me, rosters)
    return ranker, snap


# --- moves -------------------------------------------------------------------

def test_moves_change_the_current_rosters(store):
    league = _drafted_league(store)
    draft = current_rosters(league)
    mine, theirs = draft[0], draft[1]
    free = POOL[50]["name"]

    store.add_move(USER, league["id"], {"kind": "add", "team": 1, "add": [free], "drop": [mine[0]]})
    store.add_move(USER, league["id"], {"kind": "trade", "team": 1, "partner": 2, "drop": [mine[1]], "add": [theirs[0]]})
    rosters = current_rosters(store.get(USER, league["id"]))

    assert free in rosters[0] and mine[0] not in rosters[0]
    assert theirs[0] in rosters[0] and mine[1] in rosters[1] and theirs[0] not in rosters[1]
    assert sum(map(len, rosters)) == sum(map(len, draft))


def test_moves_that_dont_fit_are_refused(store):
    league = _drafted_league(store)
    draft = current_rosters(league)
    with pytest.raises(ManualLeagueError, match="doesn't have"):
        store.add_move(USER, league["id"], {"kind": "drop", "team": 1, "drop": [draft[1][0]]})
    with pytest.raises(ManualLeagueError, match="already on"):
        store.add_move(USER, league["id"], {"kind": "add", "team": 1, "add": [draft[2][0]]})
    with pytest.raises(ManualLeagueError, match="itself"):
        store.add_move(USER, league["id"], {"kind": "trade", "team": 1, "partner": 1, "add": ["x"], "drop": ["y"]})
    with pytest.raises(ManualLeagueError):
        store.add_move(USER, league["id"], {"kind": "steal", "team": 1})
    assert store.get(USER, league["id"])["moves"] == []


def test_a_move_a_later_one_depends_on_cant_be_deleted(store):
    league = _drafted_league(store)
    free = POOL[50]["name"]
    store.add_move(USER, league["id"], {"kind": "add", "team": 1, "add": [free]})
    store.add_move(USER, league["id"], {"kind": "drop", "team": 1, "drop": [free]})
    first, second = store.get(USER, league["id"])["moves"]

    with pytest.raises(ManualLeagueError, match="depends"):
        store.delete_move(USER, league["id"], first["id"])
    store.delete_move(USER, league["id"], second["id"])
    store.delete_move(USER, league["id"], first["id"])
    assert store.get(USER, league["id"])["moves"] == []


def test_leagues_saved_before_moves_existed_still_load(store):
    league = _drafted_league(store)
    league.pop("moves")
    assert current_rosters(league) == snapshots.from_manual(league).rosters


# --- analyzer ----------------------------------------------------------------

def test_standings_rank_every_category_and_sum_points():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap).report()
    teams = report["teams"]
    n = len(teams)
    for c in report["categories"]:
        assert sorted(t["ranks"][c] for t in teams)[0] == 1
    for t in teams:
        assert t["points"] == sum(n - r + 1 for r in t["ranks"].values())
    assert sorted(t["place"] for t in teams) == list(range(1, n + 1))
    # TO: fewer is better
    best_to = min(teams, key=lambda t: t["values"]["TO"])
    assert best_to["ranks"]["TO"] == 1


def test_punted_categories_dont_count_for_points():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap, punts=["FT%"]).report()
    me = report["teams"][snap.my_team]
    n = len(report["teams"])
    assert me["points"] == sum(n - r + 1 for c, r in me["ranks"].items() if c != "FT%")
    assert next(r for r in report["my_categories"] if r["category"] == "FT%")["punted"]


def test_trades_raise_my_points_and_are_fair_to_the_partner():
    ranker, snap = _snapshot_league()
    analyzer = SeasonAnalyzer(ranker, snap)
    trades = analyzer.trades()
    assert trades
    for t in trades:
        assert t["points_gain"] > 0
        assert t["their_value_change"] >= -0.75
        assert t["partner"] != snap.my_team
        assert set(t["give"]) <= set(snap.rosters[snap.my_team])
        assert set(t["get"]) <= set(snap.rosters[t["partner"]])
    assert [t["points_gain"] for t in trades] == sorted((t["points_gain"] for t in trades), reverse=True)


def test_a_lopsided_deal_is_never_suggested():
    ranker, snap = _snapshot_league()
    analyzer = SeasonAnalyzer(ranker, snap)
    # Asking the best team for its best player in exchange for my worst one
    trades = analyzer.trades()
    worst = analyzer.drops()[0]["name"]
    stars = {p["name"] for team in analyzer.players for p in team[:1]}
    assert not any(t["give"] == [worst] and t["get"][0] in stars for t in trades)


def test_pickups_are_free_agents_and_drops_are_mine():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap).report()
    rostered = set(snap.rostered())
    assert report["pickups"]
    for p in report["pickups"]:
        assert p["add"] not in rostered
        assert p["drop"] in snap.rosters[snap.my_team]
    assert all(d["name"] in snap.rosters[snap.my_team] for d in report["drops"])


def test_unknown_players_are_reported_not_counted():
    ranker, snap = _snapshot_league()
    snap.rosters[snap.my_team].append("Nobody Atall")
    report = SeasonAnalyzer(ranker, snap).report()
    assert report["unmatched"] == ["Nobody Atall"]


# --- Jev and the brief -------------------------------------------------------

def test_without_jev_the_best_move_stands():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap).report()
    rec = jev_advisor.recommend(report)
    best = max(report["trades"] + report["pickups"], key=lambda m: m["points_gain"])
    assert rec["source"] == "engine"
    assert rec["move"]["points_gain"] == best["points_gain"]
    assert "JEV_API_KEY" in rec["note"]


def test_jev_choice_is_used_when_it_answers():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap).report()
    options = [jev_advisor.describe(m) for m in jev_advisor.candidate_moves(report)]
    chosen = options[-1]

    class Answer:
        choice, confidence = chosen, 0.8
        probabilities = {chosen: 0.8, options[0]: 0.2}

    class Client:
        def system_one(self, state, questions):
            assert chosen in questions["pick"].criteria
            return type("R", (), {"choices": {"pick": Answer}})()

    rec = jev_advisor.recommend(report, client=Client())
    assert rec["source"] == "jev" and rec["text"] == chosen and rec["confidence"] == 0.8


def test_brief_is_written_from_the_report_and_cached():
    ranker, snap = _snapshot_league()
    report = SeasonAnalyzer(ranker, snap).report()
    llm = FakeLLMClient("## What's working\nREB")
    assert report_writer.write_brief(llm, report).startswith("## What's working")
    sent = llm.calls[0][1]["content"]
    assert report["my_team"]["name"] in sent and '"teams"' not in sent

    briefs = report_writer.BriefStore(use_firestore=False)
    digest = report_writer.report_hash(report, None)
    briefs.put(USER, snap.key, digest, "text")
    assert briefs.get(USER, snap.key)["hash"] == digest
    assert briefs.get("someone-else", snap.key) is None


# --- in-season stats ---------------------------------------------------------

def test_current_season_weight_grows_with_games():
    prior = [{**_player("Joe Smith", False, 1, gp=70), "PTS": 10.0}]
    early = {1: {**prior[0], "GP": 3.0, "PTS": 30.0}}
    later = {1: {**prior[0], "GP": 40.0, "PTS": 30.0}}
    pts_early = player_pool.blend_current(prior, early)[0]["PTS"]
    pts_later = player_pool.blend_current(prior, later)[0]["PTS"]
    assert 10 < pts_early < pts_later < 30


def test_rookies_join_the_pool_with_scaled_games():
    prior = [_player("Joe Smith", False, 1, gp=70)]
    current = {1: {**prior[0], "GP": 10.0}, 2: {**_player("New Guy", True, 2), "GP": 5.0}}
    pool = player_pool.blend_current(prior, current)
    rookie = next(p for p in pool if p["name"] == "New Guy")
    assert rookie["GP"] == pytest.approx(5.0 * 70 / 10.0)


def test_inseason_pool_falls_back_when_the_feed_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(player_pool, "POOL_DIR", tmp_path)
    monkeypatch.setattr(player_pool, "_inseason", {})
    monkeypatch.setattr(player_pool, "_retry_at", 0.0)
    monkeypatch.setattr(player_pool, "load_player_pool", lambda: POOL)

    def down(season):
        raise RuntimeError("feed down")

    assert player_pool.load_inseason_pool("2026-11-01", fetch=down) is POOL
    current = {p["nba_id"]: {**p, "GP": 10.0} for p in POOL[:5]}
    monkeypatch.setattr(player_pool, "_retry_at", 0.0)
    pool = player_pool.load_inseason_pool("2026-11-02", fetch=lambda s: current)
    assert pool is not POOL and (tmp_path / "player_pool_inseason.json").exists()
    # Same day, new process: read back from the store, no fetch
    monkeypatch.setattr(player_pool, "_inseason", {})
    assert player_pool.load_inseason_pool("2026-11-02", fetch=down) == pool


# --- routes ------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    routes = importlib.import_module("appl.router.season_routes")
    monkeypatch.setattr(service, "load_inseason_pool", lambda: POOL)
    monkeypatch.setattr(service, "_rankers", {})

    store = ManualLeagueStore(tmp_path)
    llm = FakeLLMClient("What's working: rebounds.")
    router = routes.SeasonRouter(store, report_writer.BriefStore(use_firestore=False), lambda: llm)
    static = str(Path(routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)
    app.secret_key = "test"
    app.register_blueprint(router.get_bp())
    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["user_id"] = USER
    league = store.create(USER, {"name": "Friends", "num_teams": 4, "roster_size": 6, "my_slot": 1})
    for p in POOL[:24]:
        store.add_pick(USER, league["id"], p["name"])
    return type("Env", (), {"http": test_client, "id": league["id"], "store": store, "llm": llm})


def test_page_and_report_for_a_manual_league(client):
    assert client.http.get(f"/season/manual/{client.id}").status_code == 200
    assert client.http.get("/season/manual/aaaaaaaaaaaa").status_code == 302
    data = client.http.get(f"/season/manual/{client.id}/report?punts=FT%25").get_json()
    assert data["punts"] == ["FT%"]
    assert len(data["teams"]) == 4
    assert len(data["manual"]["rosters"][0]["players"]) == 6
    assert data["recommendation"] is None


def test_recording_a_move_through_the_api(client):
    data = client.http.get(f"/season/manual/{client.id}/report").get_json()
    mine = data["my_team"]["players"]
    free = POOL[60]["name"]
    response = client.http.post(f"/season/manual/{client.id}/moves",
                                json={"kind": "add", "team": 1, "add": [free.lower()], "drop": [mine[0]]})
    assert response.status_code == 200
    data = client.http.get(f"/season/manual/{client.id}/report").get_json()
    assert free in data["my_team"]["players"] and mine[0] not in data["my_team"]["players"]

    move_id = data["manual"]["moves"][0]["id"]
    assert client.http.delete(f"/season/manual/{client.id}/moves/{move_id}").status_code == 200
    bad = client.http.post(f"/season/manual/{client.id}/moves", json={"kind": "drop", "team": 1, "drop": [free]})
    assert bad.status_code == 400


def test_unknown_pickup_needs_confirmation(client):
    response = client.http.post(f"/season/manual/{client.id}/moves", json={"kind": "add", "add": ["Zzz Qqq"]})
    assert response.status_code == 400 and response.get_json()["unknown_player"]
    forced = client.http.post(f"/season/manual/{client.id}/moves", json={"kind": "add", "add": ["Zzz Qqq"], "force": True})
    assert forced.status_code == 200


def test_brief_is_cached_until_the_league_changes(client):
    first = client.http.post(f"/season/manual/{client.id}/brief", json={}).get_json()
    second = client.http.post(f"/season/manual/{client.id}/brief", json={}).get_json()
    assert first["text"] == "What's working: rebounds."
    assert first["cached"] is False and second["cached"] is True
    assert len(client.llm.calls) == 1
    refreshed = client.http.post(f"/season/manual/{client.id}/brief", json={"refresh": True}).get_json()
    assert refreshed["cached"] is False and len(client.llm.calls) == 2


def test_yahoo_report_needs_a_yahoo_login(client):
    assert client.http.get("/season/yahoo/123.l.456/report").status_code == 401


def test_yahoo_snapshot_reads_every_roster():
    class Team:
        def __init__(self, names):
            self.names = names

        def roster(self):
            return [{"name": n} for n in self.names]

    class League:
        def settings(self):
            return {"name": "Yahoo L"}

        def teams(self):
            return {"t.2": {"name": "Them"}, "t.1": {"name": "Us", "is_owned_by_current_login": 1}}

        def team_key(self):
            return "t.2"

        def stat_categories(self):
            return [{"display_name": "PTS"}, {"display_name": "ST"}]

        def to_team(self, key):
            return Team(["A"] if key == "t.1" else ["B", "C"])

    snapshots._yahoo_cache.clear()
    snap = snapshots.from_yahoo(League(), "L1")
    assert snap.team_names == ["Us", "Them"] and snap.my_team == 0
    assert snap.rosters == [["A"], ["B", "C"]]
    assert snap.categories == ["PTS", "STL"]


# --- chat for manual leagues -------------------------------------------------

class FakeIndexer:
    def __init__(self):
        self.calls = []

    def update_league_files(self, league_id, files):
        self.calls.append((league_id, files))
        return f"league_{league_id}"


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setattr(service, "load_inseason_pool", lambda: POOL)
    monkeypatch.setattr(service, "_rankers", {})
    monkeypatch.setattr(service, "_indexed", {})


def test_manual_league_files_cover_the_league(store, pool):
    league = _drafted_league(store)
    free = POOL[50]["name"]
    store.add_move(USER, league["id"], {"kind": "add", "team": 1, "add": [free]})
    store.add_note(USER, league["id"], "Team 2 is punting FT%")
    files = service.manual_league_files(store.get(USER, league["id"]))

    assert {"league_settings", "team_rosters", "standing", "my_team_analysis", "free_agents",
            "draft_results", "transactions", "league_notes"} <= set(files)
    my_roster = next(t for t in files["team_rosters"] if t["is_my_team"])
    assert free in [p["name"] for p in my_roster["players"]]
    assert my_roster["players"][0]["per_game"]["PTS"] > 0
    assert files["transactions"][0]["added_or_received"] == [free]
    assert files["league_notes"][0]["text"] == "Team 2 is punting FT%"
    assert free not in [p["name"] for p in files["free_agents"]]
    assert len(files["draft_results"]) == 12


def test_indexing_uses_the_manual_chat_id_and_skips_unchanged_leagues(store, pool):
    league = _drafted_league(store)
    indexer = FakeIndexer()
    collection = service.index_manual_league(indexer, league)
    service.index_manual_league(indexer, league)
    assert collection == f"league_manual-{league['id']}"
    assert [c[0] for c in indexer.calls] == [f"manual-{league['id']}"]

    store.add_note(USER, league["id"], "changed")
    service.index_manual_league(indexer, store.get(USER, league["id"]))
    assert len(indexer.calls) == 2


def test_chat_access_for_manual_leagues(store):
    from appl.ai.access import CurrentUser, SessionAccess

    league = _drafted_league(store)

    class NoYahoo:
        def league_exist_for_user(self, league_id, yahoo_id):
            raise AssertionError("manual leagues never ask Yahoo")

    access = SessionAccess(NoYahoo, store)
    owner, other = CurrentUser(user_id=USER), CurrentUser(user_id="someone-else")
    assert access.can_access_league(owner, f"manual-{league['id']}")
    assert not access.can_access_league(other, f"manual-{league['id']}")
    assert not access.can_access_league(owner, "manual-aaaaaaaaaaaa")
    assert not access.can_access_league(owner, "manual-../../x")
    assert not SessionAccess(NoYahoo).can_access_league(owner, f"manual-{league['id']}")


def test_opening_the_manual_chat_indexes_and_redirects(store, pool, monkeypatch):
    main_routes = importlib.import_module("appl.router.main_routes")
    started = []
    monkeypatch.setattr(main_routes, "index_manual_league_async", lambda indexer, league: started.append(league["id"]))

    league = _drafted_league(store)
    static = str(Path(main_routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)
    app.secret_key = "test"
    app.register_blueprint(main_routes.MainRouter(FakeIndexer(), store).get_bp())
    http = app.test_client()
    with http.session_transaction() as session:
        session["user_id"] = USER

    response = http.get(f"/ai-chat/manual/{league['id']}")
    assert response.status_code == 302
    assert response.location.startswith(f"/agent?league_id=manual-{league['id']}&session_id=")
    assert started == [league["id"]]
    assert http.get("/ai-chat/manual/aaaaaaaaaaaa").location == "/manual"

    page = http.get(f"/agent?league_id=manual-{league['id']}&session_id=s").get_data(as_text=True)
    assert f'/ai-chat/manual/{league["id"]}' in page and f'/season/manual/{league["id"]}' in page
    assert f'"manual-{league["id"]}"' in page  # the chat posts this league id


def test_manual_season_page_shows_the_league_tabs(client):
    page = client.http.get(f"/season/manual/{client.id}").get_data(as_text=True)
    assert f"/ai-chat/manual/{client.id}" in page and f'href="/manual/{client.id}"' in page


# --- streaming ---------------------------------------------------------------

def _games(day, *matchups):
    return {day: [{"home_team": h, "away_team": a, "game_id": "x"} for h, a in matchups]}


def test_schedule_counts_games_and_back_to_backs():
    from datetime import date
    from appl.season.schedule import Schedule, team_code

    days = {}
    for d, games in [("2026-01-05", [("Boston Celtics", "Miami Heat")]),
                     ("2026-01-06", [("Boston Celtics", "Chicago Bulls")]),
                     ("2026-01-08", [("Miami Heat", "Boston Celtics")])]:
        days.update(_games(d, *games))
    sched = Schedule(days)
    start = date(2026, 1, 5)
    assert sched.games("BOS", start) == 3
    assert sched.back_to_backs("Boston Celtics", start) == 1
    assert sched.games("CHI", start) == 1
    assert sched.games("LAL", start) == 0
    assert sched.covers(start) and not sched.covers(date(2026, 3, 1))
    assert team_code("PHO") == "PHX" and team_code("nowhere") is None


def test_streaming_prefers_more_games_and_flags_missing_schedule():
    from datetime import date
    from appl.season.schedule import Schedule

    ranker, snap = _snapshot_league()
    start = date(2026, 1, 5)
    for p in ranker.players:
        p["team"] = "BOS"
    free = [p for p in ranker.players if p["name"] not in set(snap.rostered())]
    free[0]["team"], free[1]["team"] = "MIA", "CHI"
    days = {}
    for d in range(4):
        days.update(_games(f"2026-01-0{5 + d}", ("Miami Heat", "Chicago Bulls")))
    sched = Schedule(days)

    stream = SeasonAnalyzer(ranker, snap, schedule=sched, today=start).streaming()
    assert stream["available"]
    assert {"MIA", "CHI"} >= {p["team"] for p in stream["players"]}
    assert all(p["games"] == 4 and p["back_to_backs"] == 3 for p in stream["players"])
    assert stream["players"] == sorted(stream["players"], key=lambda p: -p["score"])

    stale = SeasonAnalyzer(ranker, snap, schedule=sched, today=date(2026, 6, 1)).streaming()
    assert stale["available"] is False and stale["players"] == []
    assert SeasonAnalyzer(ranker, snap).streaming()["available"] is False


# --- injuries ----------------------------------------------------------------

def test_injury_levels_from_yahoo_status():
    assert snapshots.injury_level("INJ") == "out"
    assert snapshots.injury_level("GTD") == "questionable"
    assert snapshots.injury_level("") is None and snapshots.injury_level("NA") is None


def test_injured_free_agents_and_my_players():
    ranker, snap = _snapshot_league()
    base = SeasonAnalyzer(ranker, snap)
    best = base._free_agents(limit=3)[0]["name"]
    mine = snap.rosters[snap.my_team][0]

    snap.injuries = {best: "out", mine: "out"}
    hurt = SeasonAnalyzer(ranker, snap)
    assert best not in [p["name"] for p in hurt._free_agents(limit=10)]
    report = hurt.report()
    assert report["injuries"] == [{"name": mine, "status": "out"}]
    assert any(a["kind"] == "injury" and mine in a["text"] for a in report["advice"])

    snap.injuries = {best: "questionable"}
    assert SeasonAnalyzer(ranker, snap)._injury(best) == "questionable"


# --- matchup -----------------------------------------------------------------

def test_matchup_needs_an_opponent_then_projects_every_category():
    ranker, snap = _snapshot_league()
    assert SeasonAnalyzer(ranker, snap).matchup()["available"] is False
    assert SeasonAnalyzer(ranker, snap, opponent=snap.my_team).matchup()["available"] is False

    m = SeasonAnalyzer(ranker, snap, opponent=0).matchup()
    assert m["available"] and m["scheduled"] is False
    assert [r["category"] for r in m["categories"]] == ranker.categories
    r = m["record"]
    assert r["wins"] + r["losses"] + r["ties"] == len(ranker.categories)
    assert set(m["chase"]).isdisjoint(m["concede"])

    snap.opponent = 0
    assert SeasonAnalyzer(ranker, snap).report()["matchup"]["opponent"]["index"] == 0


def test_matchup_punts_leave_the_record_and_injuries_cost_games():
    ranker, snap = _snapshot_league()
    punted = SeasonAnalyzer(ranker, snap, punts=["BLK"], opponent=0).matchup()
    row = next(r for r in punted["categories"] if r["category"] == "BLK")
    assert row["punted"] and not row["chase"] and not row["concede"]
    assert sum(punted["record"].values()) == len(ranker.categories) - 1

    healthy = SeasonAnalyzer(ranker, snap, opponent=0).matchup()["player_games"]["mine"]
    snap.injuries = {snap.rosters[snap.my_team][0]: "out"}
    hurt = SeasonAnalyzer(ranker, snap, opponent=0).matchup()["player_games"]["mine"]
    assert hurt == round(healthy - 3.5, 1)
