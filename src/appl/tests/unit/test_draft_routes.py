import importlib
from pathlib import Path

import pytest
from flask import Flask

from appl.tests.unit.test_draft import _name, _player


SLOTS = {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 1, "Util": 3}


class FakeTracker:
    """Stands in for YahooDraftTracker. `picks` are (player, team index, cost); team 0 is you."""

    def __init__(self, auction=False, position=None, picks=None):
        self.auction, self.position, self.picks = auction, position, picks or []
        self.state_calls = []
        self.eligibility = {}  # name -> set of positions; default is a guard

    def league_info(self):
        return {
            "name": "Test League",
            "num_teams": 12,
            "roster_size": 13,
            "is_auction": self.auction,
            "slots": SLOTS,
            "stat_categories": [
                {"display_name": c}
                for c in ("FG%", "FT%", "3PTM", "PTS", "REB", "AST", "ST", "BLK", "TO")
            ],
        }

    def yahoo_ranks(self):
        return {}

    def eligible_positions(self, name):
        return self.eligibility.get(name, {"PG", "G", "Util"})

    def state(self, draft_position=None):
        self.state_calls.append(draft_position)
        picks = [
            {"pick": i + 1, "round": 1, "team_key": f"t{team}", "team_name": f"Team {team}",
             "player_name": name, "cost": cost if self.auction else None, "is_mine": team == 0}
            for i, (name, team, cost) in enumerate(self.picks)
        ]
        state = {
            "league_name": "Test League",
            "draft_status": "draft",
            "is_auction": self.auction,
            "num_teams": 12,
            "roster_size": 13,
            "picks": picks,
            "taken_names": [p["player_name"] for p in picks],
            "my_roster": [p["player_name"] for p in picks if p["is_mine"]],
        }
        if self.auction:
            teams = []
            for team in range(12):
                bought = [(n, c) for n, t, c in self.picks if t == team]
                left, open_spots = 200 - sum(c for _, c in bought), 13 - len(bought)
                teams.append({"team_key": f"t{team}", "name": f"Team {team}", "budget_left": left,
                              "spots_left": open_spots, "max_bid": max(left - open_spots, 0),
                              "is_mine": team == 0})
            state.update(
                teams=teams,
                my_budget_left=teams[0]["budget_left"],
                my_open_spots=teams[0]["spots_left"],
                league_budget_left=sum(t["budget_left"] for t in teams),
                league_budget_total=2400,
                league_spots_left=sum(t["spots_left"] for t in teams),
            )
        else:
            state.update(
                my_next_pick=3, picks_until_my_turn=2,
                needs_draft_position=self.position is None and draft_position is None,
            )
        return state


@pytest.fixture
def env(monkeypatch):
    """A Flask app with the draft blueprint, a fake Yahoo tracker and a synthetic pool."""
    routes = importlib.import_module("appl.router.draft_routes")
    from appl.draft import jev_chooser

    pool = [_player(_name("Big", i), True, i) for i in range(80)]
    pool += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    monkeypatch.setattr(routes, "load_player_pool", lambda: pool)
    monkeypatch.setattr(routes, "_rankers", {})
    monkeypatch.setattr(jev_chooser, "_cache", {})
    monkeypatch.setattr(jev_chooser, "_failed_until", 0.0)
    monkeypatch.delenv("JEV_API_KEY", raising=False)

    tracker = FakeTracker()
    monkeypatch.setattr(routes.DraftRouter, "_get_tracker", lambda self, league_id: tracker)

    static = str(Path(routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)
    app.secret_key = "test"
    app.register_blueprint(routes.DraftRouter().get_bp())
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "Tester"
    return type("Env", (), {"client": client, "tracker": tracker, "routes": routes,
                            "jev": jev_chooser, "monkeypatch": monkeypatch})


def test_page_is_served(env):
    response = env.client.get("/draft/L1")
    assert response.status_code == 200
    assert b"Draft help" in response.data


def test_live_state_returns_recommendations_and_turn_info(env):
    data = env.client.get("/draft/L1/state?punts=FT%25,TO").get_json()
    assert len(data["recommendations"]) == 25
    assert data["punts"] == ["FT%", "TO"]
    assert "STL" in data["categories"]  # Yahoo's "ST" was mapped
    assert data["my_next_pick"] == 3 and data["decision"] is None
    assert data["jev_configured"] is False


def test_mock_mode_uses_the_posted_picks(env):
    first = env.client.get("/draft/L1/state").get_json()["recommendations"][0]["name"]
    data = env.client.post(
        "/draft/L1/state",
        json={"mock": True, "mock_taken": [first], "mock_mine": [first], "punts": ["AST"]},
    ).get_json()
    assert data["mock"] is True
    assert first not in [r["name"] for r in data["recommendations"]]
    assert data["my_roster"] == [first]
    assert data["roster_profile"]["REB"] != 0


def test_draft_position_override_reaches_the_tracker(env):
    env.client.get("/draft/L1/state?draft_position=5")
    env.client.get("/draft/L1/state")
    assert env.tracker.state_calls == [5, None]


def test_auction_leagues_get_bids(env):
    env.monkeypatch.setattr(env.tracker, "auction", True)
    data = env.client.get("/draft/L1/state").get_json()
    assert data["my_budget_left"] == 200
    assert all(r["bid"] >= 1 for r in data["recommendations"])


def test_without_a_key_assist_mode_falls_back_to_the_ranking(env):
    data = env.client.get("/draft/L1/state?mode=assist&preference=a%20big").get_json()
    decision = data["decision"]
    assert decision["source"] == "engine"
    assert decision["pick"] == data["recommendations"][0]["name"]
    assert "JEV_API_KEY" in decision["note"]


def test_jev_pick_is_returned_when_the_client_answers(env):
    top = env.client.get("/draft/L1/state").get_json()["recommendations"]
    chosen = top[2]["name"]

    class Answer:
        choice, confidence = chosen, 0.9
        probabilities = {chosen: 0.9, top[0]["name"]: 0.1}

    class Client:
        def system_one(self, state, questions):
            return type("R", (), {"choices": {"pick": Answer}})()

    env.monkeypatch.setenv("JEV_API_KEY", "test")
    env.monkeypatch.setattr(env.jev, "_get_client", lambda: Client())
    data = env.client.get("/draft/L1/state?mode=auto").get_json()
    assert data["decision"]["source"] == "jev"
    assert data["decision"]["pick"] == chosen
    assert data["decision"]["needs_manager"] is False
    assert data["jev_configured"] is True


def test_unknown_mode_is_treated_as_manual(env):
    assert env.client.get("/draft/L1/state?mode=bogus").get_json()["decision"] is None


def test_unauthenticated_users_get_401(env):
    env.monkeypatch.setattr(env.routes.DraftRouter, "_get_tracker", lambda self, league_id: None)
    assert env.client.get("/draft/L1/state").status_code == 401


def test_errors_return_json_500(env):
    def boom(self, league_id):
        raise RuntimeError("yahoo down")

    env.monkeypatch.setattr(env.routes.DraftRouter, "_get_tracker", boom)
    response = env.client.get("/draft/L1/state")
    assert response.status_code == 500 and "yahoo down" in response.get_json()["error"]


# --- auction ---------------------------------------------------------------

def _top_names(env, n=5):
    return [r["name"] for r in env.client.get("/draft/L1/state").get_json()["recommendations"][:n]]


def test_auction_state_has_budget_inflation_and_two_prices(env):
    env.monkeypatch.setattr(env.tracker, "auction", True)
    data = env.client.get("/draft/L1/state?punts=FT%25").get_json()
    assert data["auction"]["max_bid"] == 200 - 13
    assert data["auction"]["inflation_pct"] == 0.0
    rec = data["recommendations"][0]
    assert rec["bid"] >= 1 and rec["market"] >= 1


def test_inflation_rises_when_stars_sell_cheap(env):
    star1, star2, star3 = _top_names(env, 3)
    env.monkeypatch.setattr(env.tracker, "auction", True)
    env.monkeypatch.setattr(env.tracker, "picks", [(star1, 3, 1), (star2, 4, 1), (star3, 5, 1)])
    data = env.client.get("/draft/L1/state").get_json()
    assert data["auction"]["inflation_pct"] > 0


def test_nominee_card_gives_a_bid_ceiling_within_the_max_bid(env):
    target = _top_names(env, 1)[0]
    env.monkeypatch.setattr(env.tracker, "auction", True)
    card = env.client.get(f"/draft/L1/state?nominee={target}").get_json()["nominee_card"]
    assert card["found"] and card["sold"] is False and card["name"] == target
    assert 1 <= card["bid_up_to"] <= card["max_bid"] == 187
    assert card["verdict"] in {"target", "fair", "overpriced"}
    assert card["rivals_who_can_pay_market"] <= 11 and len(card["richest_rivals"]) == 3


def test_nominee_card_reports_a_sale_and_unknown_names(env):
    target = _top_names(env, 1)[0]
    env.monkeypatch.setattr(env.tracker, "auction", True)
    env.monkeypatch.setattr(env.tracker, "picks", [(target, 3, 41)])
    sold = env.client.get(f"/draft/L1/state?nominee={target}").get_json()["nominee_card"]
    assert sold["sold"] is True and sold["sold_to"] == "Team 3" and sold["cost"] == 41
    unknown = env.client.get("/draft/L1/state?nominee=Nobody%20Real").get_json()["nominee_card"]
    assert unknown == {"query": "Nobody Real", "found": False}


def test_nominee_card_is_only_for_auctions(env):
    target = _top_names(env, 1)[0]
    assert env.client.get(f"/draft/L1/state?nominee={target}").get_json()["nominee_card"] is None


def test_position_report_flags_empty_slots_and_nominee_fit(env):
    first, second, nominee = _top_names(env, 3)
    env.monkeypatch.setattr(env.tracker, "auction", True)
    env.monkeypatch.setattr(env.tracker, "picks", [(first, 0, 30), (second, 0, 20)])
    env.tracker.eligibility[nominee] = {"C", "F", "PF", "Util"}
    data = env.client.get(f"/draft/L1/state?nominee={nominee}").get_json()
    assert "C" in data["positions"]["unfilled"] and "PF" in data["positions"]["unfilled"]
    assert data["nominee_card"]["fills_open_slot"] is True
    assert "C" in data["nominee_card"]["eligible"]


def test_mock_auction_tracks_typed_prices(env):
    env.monkeypatch.setattr(env.tracker, "auction", True)
    first = _top_names(env, 1)[0]
    data = env.client.post("/draft/L1/state", json={
        "mock": True, "mock_taken": [first], "mock_mine": [first], "mock_costs": {first: 55},
    }).get_json()
    assert data["my_budget_left"] == 145 and data["auction"]["max_bid"] == 145 - 12
    assert data["league_budget_left"] == 2400 - 55


def test_player_list_for_the_search_box(env):
    names = env.client.get("/draft/L1/players").get_json()["players"]
    assert len(names) > 100 and names == sorted(names)


# --- the Draft tab -----------------------------------------------------------

def test_draft_page_has_the_ask_and_draft_tabs_with_draft_active(env):
    html = env.client.get("/draft/L1").get_data(as_text=True)
    assert 'class="league-tabs"' in html
    assert 'href="/ai-chat/L1"' in html and 'href="/draft/L1"' in html
    draft_tab = html[html.index('href="/draft/L1"'):].split("</a>")[0]
    ask_tab = html[html.index('href="/ai-chat/L1"'):].split("</a>")[0]
    assert 'class="active"' in draft_tab and 'class="active"' not in ask_tab


def test_league_ids_in_the_tabs_are_escaped(env):
    html = env.client.get('/draft/L1"><script>x</script>').get_data(as_text=True)
    assert "<script>x</script>" not in html


def test_the_draft_page_uses_the_shared_site_layout(env):
    html = env.client.get("/draft/L1").get_data(as_text=True)
    assert "Fantasy Basketball Helper" in html and 'href="/static/theme.css"' in html
    assert html.count("<header") == 1 and html.count("<!DOCTYPE") == 1
