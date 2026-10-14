"""Roster spots by position: settings, validation, and the "which positions do I still need" check."""
import importlib
from pathlib import Path

import pytest
from flask import Blueprint, Flask

from appl.draft.manual_league import ManualDraftTracker, ManualLeagueError, ManualLeagueStore, clean_settings
from appl.draft.player_pool import blend_seasons, parse_espn_athletes
from appl.draft.positions import (
    DEFAULT_SLOTS,
    clean_slots,
    eligible_from_listed_position,
    roster_size,
    starting_slots,
)
from appl.tests.unit.test_draft import _name, _player

USER = "slots-tester"


# --- the position rules --------------------------------------------------------

def test_every_position_gets_a_count_and_missing_ones_are_zero():
    slots = clean_slots({"PG": "2", "C": 1})
    assert slots["PG"] == 2 and slots["C"] == 1
    assert slots["SG"] == 0 and set(slots) == set(DEFAULT_SLOTS)


def test_missing_positions_keep_their_current_value_when_editing():
    slots = clean_slots({"C": 2}, fallback=DEFAULT_SLOTS)
    assert slots["C"] == 2 and slots["Util"] == 3 and slots["BN"] == 3


@pytest.mark.parametrize("raw", [{"PG": -1}, {"PG": 16}, {"PG": "two"}, {"C": 1.5}, "PG=1", None])
def test_bad_counts_are_refused(raw):
    with pytest.raises(ValueError):
        clean_slots(raw)


def test_roster_size_counts_starters_and_bench_but_not_the_injured_list():
    assert roster_size(DEFAULT_SLOTS) == 13
    assert starting_slots(DEFAULT_SLOTS) == {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 1, "Util": 3}


def test_listed_positions_map_to_the_spots_they_can_fill():
    assert eligible_from_listed_position("C") == {"C", "Util"}
    assert eligible_from_listed_position("PG") == {"PG", "G", "Util"}
    assert eligible_from_listed_position("G") == {"PG", "SG", "G", "Util"}
    assert eligible_from_listed_position("F") == {"SF", "PF", "F", "Util"}
    assert eligible_from_listed_position("G-F") >= {"PG", "SG", "G", "SF", "PF", "F"}
    assert eligible_from_listed_position("") is None and eligible_from_listed_position(None) is None
    assert eligible_from_listed_position("coach") is None


# --- manual league settings ----------------------------------------------------

def test_slots_decide_the_roster_size():
    settings = clean_settings({"num_teams": 10, "slots": {"PG": 1, "C": 1, "Util": 2, "BN": 2, "IL": 1}})
    assert settings["roster_size"] == 6  # the injured list is not drafted into
    assert settings["slots"]["Util"] == 2 and settings["slots"]["SG"] == 0


def test_leagues_without_slots_keep_a_plain_roster_size():
    settings = clean_settings({"num_teams": 10, "roster_size": 9})
    assert settings["roster_size"] == 9 and settings["slots"] is None


def test_slots_win_over_a_roster_size_sent_with_them():
    assert clean_settings({"roster_size": 20, "slots": {"PG": 2, "BN": 1}})["roster_size"] == 3


def test_editing_one_position_keeps_the_rest_and_updates_the_roster_size():
    store = ManualLeagueStore(directory=Path("unused"), backend=_MemoryBackend())
    league = store.create(USER, {"num_teams": 4, "slots": DEFAULT_SLOTS})
    updated = store.update_settings(USER, league["id"], {"slots": {"C": 2}})
    assert updated["slots"]["C"] == 2 and updated["slots"]["PG"] == 1
    assert updated["roster_size"] == 14


@pytest.mark.parametrize("slots", [{"PG": 0}, {"PG": 15, "SG": 15, "G": 1}])
def test_a_team_must_have_between_one_and_thirty_roster_spots(slots):
    # {"PG": 0} alone leaves nothing; 31 spots is too many
    raw = {"slots": {k: 0 for k in DEFAULT_SLOTS} | slots}
    with pytest.raises(ManualLeagueError):
        clean_settings(raw)


def test_a_bad_count_is_a_friendly_manual_league_error():
    with pytest.raises(ManualLeagueError, match="PG spots must be between"):
        clean_settings({"slots": {"PG": 99}})


def test_the_tracker_reports_only_starting_spots_to_the_position_check():
    store = ManualLeagueStore(directory=Path("unused"), backend=_MemoryBackend())
    league = store.create(USER, {"num_teams": 4, "slots": DEFAULT_SLOTS})
    slots = ManualDraftTracker(league).league_info()["slots"]
    assert "BN" not in slots and "IL" not in slots and slots["Util"] == 3
    legacy = store.create(USER, {"num_teams": 4, "roster_size": 5})
    assert ManualDraftTracker(legacy).league_info()["slots"] == {}


class _MemoryBackend:
    """Just enough storage to test settings without touching disk."""

    def __init__(self):
        self.data = {}

    def read(self, user, league_id):
        import copy
        try:
            return copy.deepcopy(self.data[(user, league_id)])
        except KeyError:
            raise KeyError(league_id) from None

    def write(self, user, league):
        import copy
        self.data[(user, league["id"])] = copy.deepcopy(league)

    def list(self, user):
        return [v for (u, _), v in self.data.items() if u == user]

    def delete(self, user, league_id):
        self.data.pop((user, league_id), None)

    def modify(self, user, league_id, change):
        league = self.read(user, league_id)
        change(league)
        self.write(user, league)
        return league


# --- the page's position warning on a manual league -----------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    routes = importlib.import_module("appl.router.draft_routes")
    from appl.draft import jev_chooser

    pool = [{**_player(_name("Big", i), True, i), "pos": "C"} for i in range(40)]
    pool += [{**_player(_name("Guard", i), False, 100 + i), "pos": "G"} for i in range(60)]
    monkeypatch.setattr(routes, "load_player_pool", lambda: pool)
    monkeypatch.setattr(routes, "_rankers", {})
    monkeypatch.setattr(jev_chooser, "_cache", {})
    monkeypatch.delenv("JEV_API_KEY", raising=False)

    static = str(Path(routes.__file__).parents[1] / "static")
    app = Flask(__name__, static_folder=static, template_folder=static)
    app.secret_key = "test"
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/login", "google_login", lambda: "login")
    app.register_blueprint(auth)
    app.register_blueprint(routes.DraftRouter(ManualLeagueStore(tmp_path)).get_manual_bp())
    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["user_id"] = USER
    return test_client


def _league(client, **extra):
    slots = {"PG": 1, "C": 1, "BN": 1}
    body = {"name": "Slots", "num_teams": 4, "my_slot": 1, "slots": slots, **extra}
    return client.post("/manual/api/leagues", json=body).get_json()["id"]


def _log(client, league_id, name, **extra):
    return client.post(f"/manual/{league_id}/picks", json={"player_name": name, **extra})


def test_the_page_says_which_positions_are_still_open(client):
    league_id = _league(client)
    assert client.get(f"/manual/{league_id}/state").get_json()["positions"]["unfilled"] == ["C", "PG"]

    assert _log(client, league_id, "Guard Aa").status_code == 200  # a guard fills PG
    state = client.get(f"/manual/{league_id}/state").get_json()
    assert state["positions"]["unfilled"] == ["C"]
    assert state["manual"]["settings"]["slots"]["C"] == 1 and state["roster_size"] == 3


def test_filling_every_starting_spot_clears_the_warning(client):
    league_id = _league(client)
    _log(client, league_id, "Guard Aa")
    _log(client, league_id, "Big Aa", team=1)
    assert client.get(f"/manual/{league_id}/state").get_json()["positions"]["unfilled"] == []


def test_the_auction_bid_card_says_whether_the_nominee_fills_an_open_spot(client):
    league_id = _league(client, is_auction=True, budget=200)
    _log(client, league_id, "Guard Aa", team=1, cost=20)  # your PG
    card = client.get(f"/manual/{league_id}/state?nominee=Big Aa").get_json()["nominee_card"]
    assert card["fills_open_slot"] is True and "C" in card["eligible"]
    # a second guard has nowhere to start: PG is taken and C needs a big
    card = client.get(f"/manual/{league_id}/state?nominee=Guard Ab").get_json()["nominee_card"]
    assert card["fills_open_slot"] is False


def test_picks_can_be_edited_and_deleted_over_http(client):
    league_id = _league(client, is_auction=True, budget=200)
    _log(client, league_id, "Guard Aa", team=1, cost=20)
    edit = client.put(f"/manual/{league_id}/picks/1", json={"player_name": "Guard Aa", "team": 2, "cost": 35})
    assert edit.status_code == 200
    pick = client.get(f"/manual/{league_id}/state").get_json()["picks"][0]
    assert (pick["team_key"], pick["cost"]) == ("t1", 35)
    assert client.put(f"/manual/{league_id}/picks/7", json={"player_name": "Guard Aa", "team": 2, "cost": 5}).status_code == 400
    assert client.delete(f"/manual/{league_id}/picks/1").status_code == 200
    assert client.get(f"/manual/{league_id}/state").get_json()["picks"] == []


def test_bid_card_warns_when_the_ceiling_would_leave_you_thin(client):
    league_id = _league(client, is_auction=True, budget=200)
    card = client.get(f"/manual/{league_id}/state?nominee=Big Aa").get_json()["nominee_card"]
    assert card["walk_away_above"] == card["bid_up_to"]
    assert card["left_after_bid"] == 200 - card["bid_up_to"]
    assert card["spots_after_bid"] == 2 and "thin_after_bid" in card
    # a $1 price tag can never leave you thin; spending nearly everything on one player does
    _log(client, league_id, "Guard Aa", team=1, cost=190)
    card = client.get(f"/manual/{league_id}/state?nominee=Big Aa").get_json()["nominee_card"]
    assert card["thin_after_bid"] is True


def test_a_league_without_slots_has_no_position_check(client):
    body = {"name": "Old", "num_teams": 4, "roster_size": 3, "my_slot": 1}
    league_id = client.post("/manual/api/leagues", json=body).get_json()["id"]
    assert client.get(f"/manual/{league_id}/state").get_json()["positions"] is None


def test_settings_can_be_changed_from_the_draft_page(client):
    league_id = _league(client)
    response = client.put(f"/manual/{league_id}/settings", json={"slots": {"C": 2, "BN": 2}})
    assert response.status_code == 200
    state = client.get(f"/manual/{league_id}/state").get_json()
    assert state["manual"]["settings"]["slots"]["C"] == 2 and state["roster_size"] == 5  # PG 1 + C 2 + bench 2
    assert client.put(f"/manual/{league_id}/settings", json={"slots": {"C": 99}}).status_code == 400


# --- where the position comes from -------------------------------------------------

def _espn_row(position):
    names = {"general": ["gamesPlayed", "avgMinutes", "avgRebounds"],
             "offensive": ["avgPoints", "avgFieldGoalsMade", "avgFieldGoalsAttempted",
                           "avgThreePointFieldGoalsMade", "avgFreeThrowsMade",
                           "avgFreeThrowsAttempted", "avgAssists", "avgTurnovers"],
             "defensive": ["avgSteals", "avgBlocks"]}
    values = [("general", [60, 30, 5]), ("offensive", [20, 7, 15, 2, 4, 5, 4, 2]), ("defensive", [1, 1])]
    athlete = {"id": "1", "displayName": "Test Player", "teamShortName": "LAL"}
    if position:
        athlete["position"] = {"abbreviation": position}
    return {"categories": [{"name": n, "names": v} for n, v in names.items()],
            "athletes": [{"athlete": athlete, "categories": [{"name": n, "values": v} for n, v in values]}]}


def test_the_listed_position_is_read_from_espn():
    assert parse_espn_athletes(_espn_row("G"))[1]["pos"] == "G"
    assert parse_espn_athletes(_espn_row(None))[1]["pos"] is None


def test_blended_players_keep_the_newest_position_that_exists():
    line = {"name": "A", "team": "T", "GP": 60, "MIN": 30, "PTS": 20, "REB": 5, "AST": 5, "STL": 1,
            "BLK": 1, "TOV": 2, "FG3M": 1, "FGM": 5, "FGA": 10, "FTM": 3, "FTA": 4}
    newest, older = {1: {**line, "pos": None}}, {1: {**line, "pos": "F"}}
    assert blend_seasons([(newest, 0.7), (older, 0.3)])[0]["pos"] == "F"
    assert blend_seasons([({1: {**line, "pos": "C"}}, 0.7), (older, 0.3)])[0]["pos"] == "C"
