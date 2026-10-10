import importlib
from pathlib import Path

import pytest
from flask import Blueprint, Flask

from appl.draft.api_tokens import ApiTokenStore, FileTokenBackend
from appl.draft.manual_league import (
    ManualDraftTracker,
    ManualLeagueError,
    ManualLeagueStore,
    current_rosters,
    snake_team,
)
from appl.tests.unit.test_draft import _name, _player

USER = "user-1"


@pytest.fixture
def store(tmp_path):
    return ManualLeagueStore(tmp_path)


def _league(store, **settings):
    return store.create(USER, {"name": "Friends", "num_teams": 4, "roster_size": 3, "my_slot": 2, **settings})


def test_snake_order_reverses_each_round():
    assert [snake_team(i, 4) for i in range(8)] == [0, 1, 2, 3, 3, 2, 1, 0]


def test_create_validates_and_persists(store):
    league = _league(store)
    assert store.get(USER, league["id"])["name"] == "Friends"
    assert store.list(USER)[0]["total_picks"] == 12
    with pytest.raises(ManualLeagueError):
        store.create(USER, {"num_teams": 1})
    with pytest.raises(ManualLeagueError):
        store.create(USER, {"categories": ["nope"]})


def test_leagues_are_private_per_user_and_ids_are_not_paths(store):
    league = _league(store)
    with pytest.raises(KeyError):
        store.get("someone-else", league["id"])
    with pytest.raises(KeyError):
        store.get(USER, "../../etc/passwd")
    assert store.list("someone-else") == []


def test_snake_pick_goes_to_the_team_on_the_clock(store):
    league = _league(store)
    for name in ("A One", "B Two", "C Three", "D Four", "E Five"):
        store.add_pick(USER, league["id"], name)
    teams = [p["team"] for p in store.get(USER, league["id"])["picks"]]
    assert teams == [0, 1, 2, 3, 3]


def test_duplicate_pick_rejected_and_undo(store):
    league = _league(store)
    store.add_pick(USER, league["id"], "LeBron James")
    with pytest.raises(ManualLeagueError):
        store.add_pick(USER, league["id"], "lebron james")
    store.undo_pick(USER, league["id"])
    store.add_pick(USER, league["id"], "LeBron James")
    empty = _league(store)
    with pytest.raises(ManualLeagueError):
        store.undo_pick(USER, empty["id"])


def test_auction_pick_needs_team_and_price_within_budget(store):
    league = _league(store, is_auction=True, budget=100)
    with pytest.raises(ManualLeagueError):
        store.add_pick(USER, league["id"], "A One")
    with pytest.raises(ManualLeagueError):
        store.add_pick(USER, league["id"], "A One", team=1, cost=101)
    store.add_pick(USER, league["id"], "A One", team=2, cost=40)
    pick = store.get(USER, league["id"])["picks"][0]
    assert (pick["team"], pick["cost"]) == (1, 40)


def test_any_pick_can_be_corrected_or_deleted(store):
    league = _league(store, is_auction=True, budget=100)
    for name, team, cost in (("A One", 1, 10), ("B Two", 2, 20), ("C Three", 3, 30)):
        store.add_pick(USER, league["id"], name, team=team, cost=cost)

    store.edit_pick(USER, league["id"], 2, "B Two", team=4, cost=25)
    pick = store.get(USER, league["id"])["picks"][1]
    assert (pick["team"], pick["cost"]) == (3, 25)

    # keeping the same player is fine; taking another pick's player is not
    store.edit_pick(USER, league["id"], 1, "A One", team=1, cost=11)
    with pytest.raises(ManualLeagueError):
        store.edit_pick(USER, league["id"], 1, "c three", team=1, cost=11)
    with pytest.raises(ManualLeagueError):
        store.edit_pick(USER, league["id"], 9, "A One", team=1, cost=11)

    store.delete_pick(USER, league["id"], 1)
    picks = store.get(USER, league["id"])["picks"]
    assert [p["player_name"] for p in picks] == ["B Two", "C Three"]
    with pytest.raises(ManualLeagueError):
        store.delete_pick(USER, league["id"], 3)


def test_notes_remember_the_phase(store):
    league = _league(store)
    store.add_note(USER, league["id"], "Team 3 hates bigs")
    store.add_pick(USER, league["id"], "A One")
    store.add_note(USER, league["id"], "Trade offer")
    store.set_status(USER, league["id"], "finished")
    store.add_note(USER, league["id"], "Waiver plan")
    notes = store.get(USER, league["id"])["notes"]
    assert [n["phase"] for n in notes] == ["before", "during", "after"]
    store.delete_note(USER, league["id"], notes[0]["id"])
    assert len(store.get(USER, league["id"])["notes"]) == 2
    with pytest.raises(ManualLeagueError):
        store.add_note(USER, league["id"], "   ")


def test_settings_cannot_orphan_picks_or_flip_draft_type(store):
    league = _league(store)
    store.add_pick(USER, league["id"], "A One", team=4)
    with pytest.raises(ManualLeagueError):
        store.update_settings(USER, league["id"], {"num_teams": 3})
    with pytest.raises(ManualLeagueError):
        store.update_settings(USER, league["id"], {"is_auction": True})
    updated = store.update_settings(USER, league["id"], {"team_names": ["Me", "Bob"], "categories": ["PTS", "ST"]})
    assert updated["team_names"][:3] == ["Me", "Bob", "Team 3"]
    assert updated["categories"] == ["PTS", "STL"]


def test_tracker_snake_state(store):
    league = _league(store)  # 4 teams, you are slot 2
    store.add_pick(USER, league["id"], "A One")
    league = store.add_pick(USER, league["id"], "B Two")  # yours
    state = ManualDraftTracker(league).state()
    assert state["my_roster"] == ["B Two"]
    assert state["my_next_pick"] == 7 and state["picks_until_my_turn"] == 4
    assert state["manual"]["on_the_clock"]["index"] == 2
    assert state["needs_draft_position"] is False


def test_tracker_auction_state_tracks_budgets(store):
    league = _league(store, is_auction=True, budget=100)
    store.add_pick(USER, league["id"], "A One", team=2, cost=30)
    league = store.add_pick(USER, league["id"], "B Two", team=1, cost=50)
    state = ManualDraftTracker(league).state()
    assert state["my_budget_left"] == 70
    assert state["league_budget_total"] == 400 and state["league_budget_left"] == 320
    mine = next(t for t in state["teams"] if t["is_mine"])
    assert mine["max_bid"] == 70 - 2  # keep $1 for each of the 2 open spots


@pytest.fixture
def client(tmp_path, monkeypatch):
    routes = importlib.import_module("appl.router.draft_routes")
    from appl.draft import jev_chooser

    pool = [_player(_name("Big", i), True, i) for i in range(80)]
    pool += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    monkeypatch.setattr(routes, "load_player_pool", lambda: pool)
    monkeypatch.setattr(routes, "_rankers", {})
    monkeypatch.setattr(jev_chooser, "_cache", {})
    monkeypatch.delenv("JEV_API_KEY", raising=False)

    static = str(Path(routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)  # as in the real app
    app.secret_key = "test"
    app.config["TESTING"] = True
    home = Blueprint("main", __name__)
    home.add_url_rule("/", "homepage", lambda: "home")  # the target of the login redirect
    app.register_blueprint(home)
    tokens = ApiTokenStore(FileTokenBackend(tmp_path / "tokens.json"))
    app.register_blueprint(routes.DraftRouter(ManualLeagueStore(tmp_path), tokens).get_manual_bp())
    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["user_id"] = USER
    return test_client


def _create(client, **extra):
    body = {"name": "Friends", "num_teams": 4, "roster_size": 3, "my_slot": 1, **extra}
    return client.post("/manual/api/leagues", json=body).get_json()["id"]


def test_pages_are_served(client):
    assert client.get("/manual").status_code == 200
    league_id = _create(client)
    assert b"Log a pick" in client.get(f"/manual/{league_id}").data
    assert client.get("/manual/aaaaaaaaaaaa").status_code == 302  # unknown league -> list


def test_logged_pick_leaves_the_recommendations_and_joins_my_roster(client):
    league_id = _create(client)
    state = client.get(f"/manual/{league_id}/state").get_json()
    best = state["recommendations"][0]["name"]
    assert state["manual"]["on_the_clock"]["name"] == "Team 1"

    response = client.post(f"/manual/{league_id}/picks", json={"player_name": best.lower()})
    assert response.status_code == 200

    state = client.get(f"/manual/{league_id}/state").get_json()
    assert best not in [r["name"] for r in state["recommendations"]]
    assert state["my_roster"] == [best]  # stored with the pool's spelling; slot 1 picks first
    assert state["manual"]["rosters"][0]["players"][0]["name"] == best


def test_bad_input_gets_a_readable_error(client):
    league_id = _create(client)
    assert client.post(f"/manual/{league_id}/picks", json={"player_name": ""}).status_code == 400
    assert client.post("/manual/api/leagues", json={"num_teams": 99}).status_code == 400
    assert client.post("/manual/bbbbbbbbbbbb/notes", json={"text": "x"}).status_code == 404


def test_notes_and_status_round_trip(client):
    league_id = _create(client)
    client.post(f"/manual/{league_id}/notes", json={"text": "Rival is punting FT"})
    client.put(f"/manual/{league_id}/status", json={"status": "finished"})
    state = client.get(f"/manual/{league_id}/state").get_json()
    assert state["manual"]["notes"][0]["text"] == "Rival is punting FT"
    assert state["draft_status"] == "finished"


def test_changing_categories_rebuilds_the_ranking(client):
    league_id = _create(client)
    before = client.get(f"/manual/{league_id}/state").get_json()["categories"]
    client.put(f"/manual/{league_id}/settings", json={"categories": ["PTS", "REB"]})
    after = client.get(f"/manual/{league_id}/state").get_json()["categories"]
    assert len(before) == 9 and after == ["PTS", "REB"]


def test_unauthenticated_requests_are_redirected(client):
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/manual/api/leagues").status_code == 302


def test_unknown_name_is_not_logged_without_confirmation(client):
    league_id = _create(client)
    response = client.post(f"/manual/{league_id}/picks", json={"player_name": "aa"})
    body = response.get_json()
    assert response.status_code == 400 and body["unknown_player"]
    assert "Big Aa" in body["suggestions"]
    assert client.get(f"/manual/{league_id}/state").get_json()["picks"] == []

    # A rookie with no stats can still be logged on purpose
    assert client.post(f"/manual/{league_id}/picks", json={"player_name": "New Rookie", "force": True}).status_code == 200
    assert client.get(f"/manual/{league_id}/state").get_json()["my_roster"] == ["New Rookie"]


def test_duplicate_pick_says_who_has_him(client):
    league_id = _create(client)
    client.post(f"/manual/{league_id}/picks", json={"player_name": "Big Aa"})
    response = client.post(f"/manual/{league_id}/picks", json={"player_name": "big aa"})
    assert response.status_code == 400
    assert "pick #1, Team 1" in response.get_json()["error"]


# --- importing a finished league (e.g. from screenshots, via Claude Code) -------

def _teams(*rosters):
    return [{"name": f"T{i}", "players": list(r)} for i, r in enumerate(rosters)]


def test_import_stores_rosters_as_a_finished_draft(store):
    league = store.import_league(USER, {
        "name": "Shots", "my_team": "t1",
        "teams": _teams(["A", "B", "C"], ["D", "E"], ["F"]),
    })
    assert league["status"] == "finished" and league["num_teams"] == 3
    assert league["my_slot"] == 2  # matched by name, ignoring case
    assert league["roster_size"] == 3  # the biggest roster, when no slots are given
    assert current_rosters(store.get(USER, league["id"])) == [["A", "B", "C"], ["D", "E"], ["F"]]


def test_import_refuses_a_player_on_two_teams_and_unknown_teams(store):
    with pytest.raises(ManualLeagueError, match="two teams"):
        store.import_league(USER, {"my_team": 1, "teams": _teams(["A"], ["a"])})
    with pytest.raises(ManualLeagueError, match="No team called"):
        store.import_league(USER, {"my_team": "Nobody", "teams": _teams(["A"], ["B"])})
    with pytest.raises(ManualLeagueError):
        store.import_league(USER, {"my_team": 1, "teams": _teams(["A"])})
    assert store.list(USER) == []


def _token(client):
    return client.post("/manual/api/tokens", json={"label": "cc"}).get_json()["token"]


def test_a_token_imports_a_league_for_its_owner_without_a_session(client):
    token = _token(client)
    with client.session_transaction() as session:
        session.clear()
    auth = {"Authorization": f"Bearer {token}"}
    body = {"name": "Shots", "my_team": 1, "teams": _teams(["big aa", "Guard Ab"], ["Big Ac"])}

    dry = client.post("/manual/api/import", json={**body, "dry_run": True}, headers=auth).get_json()
    assert dry["unknown"] == [] and dry["teams"][0]["players"][0]["name"] == "Big Aa"
    assert client.get("/manual/api/leagues", headers=auth).get_json()["leagues"] == []  # dry run saves nothing

    response = client.post("/manual/api/import", json=body, headers=auth)
    assert response.status_code == 201
    league_id = response.get_json()["id"]
    assert response.get_json()["links"]["season"] == f"/season/manual/{league_id}"

    with client.session_transaction() as session:  # the same Google user sees it in the browser
        session["user_id"] = USER
    state = client.get(f"/manual/{league_id}/state").get_json()
    assert state["my_roster"] == ["Big Aa", "Guard Ab"] and state["draft_status"] == "finished"


def test_import_reports_unknown_names_and_saves_only_when_forced(client):
    auth = {"Authorization": f"Bearer {_token(client)}"}
    body = {"my_team": 1, "teams": _teams(["Big Aa", "Zzqx Unknownson"], ["Big Ab"])}
    response = client.post("/manual/api/import", json=body, headers=auth)
    assert response.status_code == 400 and response.get_json()["unknown"] == ["Zzqx Unknownson"]
    assert client.get("/manual/api/leagues").get_json()["leagues"] == []
    assert client.post("/manual/api/import", json={**body, "force": True}, headers=auth).status_code == 201


def test_bad_or_revoked_tokens_are_refused_and_tokens_cant_make_tokens(client):
    token = _token(client)
    assert client.get("/manual/api/leagues", headers={"Authorization": "Bearer fbh_nope"}).status_code == 401
    (listed,) = client.get("/manual/api/tokens").get_json()["tokens"]
    assert token not in str(listed) and listed["hint"] == token[-4:]

    with client.session_transaction() as session:
        session.clear()
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/manual/api/tokens", json={}, headers=auth).status_code == 302  # browser login only

    with client.session_transaction() as session:
        session["user_id"] = "someone-else"
    assert client.delete(f"/manual/api/tokens/{listed['id']}").status_code == 404  # not theirs
    with client.session_transaction() as session:
        session["user_id"] = USER
    assert client.delete(f"/manual/api/tokens/{listed['id']}").status_code == 200
    assert client.get("/manual/api/leagues", headers=auth).status_code == 401
