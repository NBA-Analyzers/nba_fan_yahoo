"""The league analysis page and its JSON, for manual leagues end to end."""

from types import SimpleNamespace as NS

import pytest

from appl.tests.unit.test_matchup_routes import make_client

SECTIONS = {"power_rankings", "buy_sell", "trade_ideas", "playoffs",
            "league_name", "scoring", "my_team", "teams", "categories", "punts", "warnings"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch)


def test_the_page_renders_with_its_tab_selected(client):
    response = client.http.get(f"/season/manual/{client.id}/analysis")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'href="/season/manual/{client.id}/analysis" class="active"' in html
    assert 'id="panel_trade"' in html and 'id="panel_power"' in html and 'id="panel_playoffs"' in html


def test_every_league_page_links_to_the_analysis(client):
    html = client.http.get(f"/season/manual/{client.id}/matchup").get_data(as_text=True)
    assert f'href="/season/manual/{client.id}/analysis"' in html
    html = client.http.get("/season/yahoo/123/matchup").get_data(as_text=True)
    assert 'href="/season/yahoo/123/analysis"' in html


def test_unknown_leagues_and_kinds_are_sent_away(client, tmp_path, monkeypatch):
    assert client.http.get("/season/manual/aaaaaaaaaaaa/analysis").headers["Location"].endswith("/manual")
    assert client.http.get("/season/mystery/1/analysis").headers["Location"].endswith("/dashboard")
    espn = NS(league_repo=NS(league_exist_for_user=lambda league_id, user: False))
    other = make_client(tmp_path / "e", monkeypatch, espn=espn)
    assert other.http.get("/season/espn/9/analysis").headers["Location"].endswith("/dashboard")


def test_the_report_has_every_section(client):
    response = client.http.get(f"/season/manual/{client.id}/analysis/report")
    data = response.get_json()
    assert response.status_code == 200
    assert set(data) == SECTIONS
    assert len(data["power_rankings"]) == 4 and data["my_team"]["index"] == 0
    assert data["buy_sell"]["available"] is False  # the fake datasets have no recent form


def test_the_report_honors_punts(client):
    data = client.http.get(f"/season/manual/{client.id}/analysis/report?punts=FT%25,BLK").get_json()
    assert data["punts"] == ["FT%", "BLK"]


def test_an_unknown_league_report_is_a_404(client):
    assert client.http.get("/season/manual/aaaaaaaaaaaa/analysis/report").status_code == 404
