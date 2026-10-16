"""The matchup page and its JSON: for manual leagues end to end, and the platform guards."""

import importlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from flask import Flask

from appl.draft.manual_league import ManualLeagueStore
from appl.season import report_writer, service
from appl.season.schedule import Schedule
from appl.tests.unit.conftest import FakeLLMClient
from appl.tests.unit.test_season import POOL, USER

SECTIONS = {"available", "week", "summary", "scoreboard", "days", "streamers", "plan",
            "profile", "contributions", "grid", "scouting",
            "league_name", "scoring", "my_team", "teams", "categories", "punts", "warnings"}


class FakeData:
    """Stands in for the nightly datasets."""

    def __init__(self, injuries=None):
        self.injuries = injuries or {}

    def injury_levels(self):
        return self.injuries

    def form(self, name):
        return None

    def risers(self, names):
        return []


def make_client(tmp_path, monkeypatch, player_data=None, espn=None):
    routes = importlib.import_module("appl.router.season_routes")
    monkeypatch.setattr(service, "load_inseason_pool", lambda: POOL)
    monkeypatch.setattr(service, "_rankers", {})
    store = ManualLeagueStore(tmp_path)
    llm = FakeLLMClient("Where you stand: ahead.")
    router = routes.SeasonRouter(store, report_writer.BriefStore(use_firestore=False), lambda: llm,
                                 schedule=Schedule({}), espn=espn, player_data=player_data or (lambda: FakeData()))
    static = str(Path(routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)
    app.secret_key = "test"
    app.register_blueprint(router.get_bp())
    http = app.test_client()
    with http.session_transaction() as session:
        session["user_id"] = USER
    league = store.create(USER, {"name": "Friends", "num_teams": 4, "roster_size": 6, "my_slot": 1})
    for p in POOL[:24]:
        store.add_pick(USER, league["id"], p["name"])
    return NS(http=http, id=league["id"], llm=llm)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch)


def report(client, query=""):
    return client.http.get(f"/season/manual/{client.id}/matchup/report{query}")


# ---------- the page ----------
def test_the_page_renders_with_its_tab_selected(client):
    response = client.http.get(f"/season/manual/{client.id}/matchup")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'href="/season/manual/{client.id}/matchup" class="active"' in html
    assert 'id="panel_prep"' in html and 'id="panel_team"' in html and 'id="panel_league"' in html


def test_unknown_leagues_and_kinds_are_sent_away(client):
    assert client.http.get("/season/manual/aaaaaaaaaaaa/matchup").headers["Location"].endswith("/manual")
    assert client.http.get("/season/mystery/1/matchup").headers["Location"].endswith("/dashboard")


def test_the_yahoo_page_links_its_tabs_to_yahoo(client):
    html = client.http.get("/season/yahoo/123/matchup").get_data(as_text=True)
    assert 'href="/season/yahoo/123"' in html and 'href="/season/yahoo/123/matchup" class="active"' in html


def test_the_espn_tabs_no_longer_point_at_yahoo(tmp_path, monkeypatch):
    espn = NS(league_repo=NS(league_exist_for_user=lambda league_id, user: league_id == "777"))
    c = make_client(tmp_path, monkeypatch, espn=espn)
    for path in ("/season/espn/777", "/season/espn/777/matchup"):
        html = c.http.get(path).get_data(as_text=True)
        assert 'href="/season/espn/777"' in html and 'href="/season/espn/777/matchup"' in html
        assert "/season/yahoo/777" not in html
    assert c.http.get("/season/espn/888/matchup").headers["Location"].endswith("/dashboard")


def test_the_season_page_links_to_matchup_prep(client):
    html = client.http.get(f"/season/manual/{client.id}").get_data(as_text=True)
    assert 'id="prep_link"' in html and f'href="/season/manual/{client.id}/matchup"' in html


# ---------- the report ----------
def test_the_report_has_every_section_for_a_picked_opponent(client):
    data = report(client, "?opponent=2").get_json()
    assert set(data) == SECTIONS
    assert data["available"] is True and data["summary"]["opponent"]["index"] == 1
    assert len(data["teams"]) == 4 and data["my_team"]["index"] == 0
    assert [r["category"] for r in data["scoreboard"]] == data["categories"]
    assert len(data["grid"]) == 3 and len(data["scouting"]) == 3
    assert len(data["contributions"]["players"]) == 6 and len(data["profile"]) == len(data["categories"])


def test_without_an_opponent_the_team_sections_still_work(client):
    data = report(client).get_json()
    assert data["available"] is False and data["scoreboard"] == [] and data["plan"] == []
    assert data["grid"] and data["profile"] and data["contributions"]["players"]


def test_punts_leave_the_matchup_and_the_grid(client):
    data = report(client, "?opponent=2&punts=BLK").get_json()
    assert data["punts"] == ["BLK"]
    assert all("BLK" not in g["categories"] for g in data["grid"])
    assert next(r for r in data["scoreboard"] if r["category"] == "BLK")["punted"] is True


def test_an_unknown_league_or_kind_is_a_404(client):
    assert client.http.get("/season/manual/aaaaaaaaaaaa/matchup/report").status_code == 404
    assert client.http.get("/season/mystery/1/matchup/report").status_code == 404


def test_yahoo_needs_a_connected_account(client):
    response = client.http.get("/season/yahoo/123/matchup/report")
    assert response.status_code == 401 and "Yahoo" in response.get_json()["error"]


def test_nightly_injuries_reach_a_manual_league(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch, player_data=lambda: FakeData({POOL[0]["name"]: "out"}))
    players = report(c, "?opponent=2").get_json()["contributions"]["players"]
    assert {p["name"]: p["injury"] for p in players}.get(POOL[0]["name"]) == "out"


def test_a_failing_data_feed_does_not_break_the_page(tmp_path, monkeypatch):
    def broken():
        raise RuntimeError("datasets are down")

    c = make_client(tmp_path, monkeypatch, player_data=broken)
    assert report(c, "?opponent=2").status_code == 200


def test_errors_do_not_leak_the_cause(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("firestore says key=abc123secret")

    monkeypatch.setattr(service, "load_inseason_pool", boom)
    monkeypatch.setattr(service, "_rankers", {})
    response = report(client, "?opponent=2")
    assert response.status_code == 500 and "abc123secret" not in response.get_data(as_text=True)


# ---------- the game plan ----------
def brief(client, query="?opponent=2", **body):
    return client.http.post(f"/season/manual/{client.id}/matchup/brief{query}", json=body)


def test_the_game_plan_is_written_once_and_then_cached(client):
    first, second = brief(client).get_json(), brief(client).get_json()
    assert first["text"] == "Where you stand: ahead."
    assert first["cached"] is False and second["cached"] is True
    assert len(client.llm.calls) == 1
    assert brief(client, refresh=True).get_json()["cached"] is False and len(client.llm.calls) == 2


def test_the_game_plan_gets_the_matchup_numbers_and_not_the_bulk(client):
    brief(client)
    system, user = client.llm.calls[0]
    assert "head-to-head" in system["content"]
    for key in ("summary", "categories", "planned_actions", "my_profile"):
        assert key in user["content"]
    assert '"grid"' not in user["content"] and '"contributions"' not in user["content"]


def test_a_different_opponent_gets_a_new_game_plan(client):
    brief(client, "?opponent=2")
    assert brief(client, "?opponent=3").get_json()["cached"] is False


def test_the_game_plan_needs_an_opponent(client):
    response = brief(client, "")
    assert response.status_code == 400 and "opponent" in response.get_json()["error"]
    assert client.llm.calls == []


def test_the_game_plan_does_not_replace_the_season_brief(client):
    brief(client)
    season = client.http.post(f"/season/manual/{client.id}/brief", json={}).get_json()
    assert season["cached"] is False  # a separate cache entry
