"""Punt suggestions that update as the team grows, and auction cash advice."""
import pytest

from appl.draft import advice
from appl.draft.ranker import DraftRanker
from appl.tests.unit.test_draft import _name, _player
from appl.tests.unit.test_draft_routes import _top_names, env  # noqa: F401  (env is a fixture)


@pytest.fixture(scope="module")
def ranker():
    pool = [_player(_name("Big", i), True, i) for i in range(80)]
    pool += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    return DraftRanker(pool, num_teams=12, roster_size=13)


def _bigs(ranker, n=3):
    return [r["name"] for r in ranker.rank(punts=["AST"], limit=n)]


# --- which category to skip ----------------------------------------------------

def test_no_suggestion_until_a_few_players_are_picked(ranker):
    assert advice.build_suggestion(ranker, [], [], []) is None
    assert advice.build_suggestion(ranker, _bigs(ranker, 1), [], []) is None


def test_suggests_the_weakest_category_and_shows_what_changes(ranker):
    roster = _bigs(ranker)
    profile = ranker.roster_profile(roster)
    suggestion = advice.build_suggestion(ranker, roster, [], roster)
    assert suggestion["category"] == min(profile, key=profile.get)
    assert suggestion["avg_z"] == profile[suggestion["category"]] <= advice.WEAK_AVG_Z
    assert len(suggestion["now"]) == len(suggestion["if_skipped"]) == 3
    assert not set(suggestion["now"]) & set(roster)  # players you already have aren't offered
    assert suggestion["now"] != suggestion["if_skipped"]


def test_only_one_category_is_suggested_and_only_while_none_is_skipped(ranker):
    roster = _bigs(ranker)
    assert advice.build_suggestion(ranker, roster, ["FT%"], roster) is None


def test_nothing_is_suggested_when_no_category_is_clearly_weak(ranker, monkeypatch):
    monkeypatch.setattr(advice, "WEAK_AVG_Z", -99)
    assert advice.build_suggestion(ranker, _bigs(ranker), [], []) is None


# --- cash advice ----------------------------------------------------------------

def _team(name, left, spots, mine=False):
    return {"name": name, "budget_left": left, "spots_left": spots,
            "max_bid": max(left - spots, 0) if spots else 0, "is_mine": mine}


def _state(mine_left=100, mine_spots=5, rivals=None, league_left=600, league_spots=30):
    teams = [_team("You", mine_left, mine_spots, True)] + (rivals if rivals is not None else [])
    return {"my_budget_left": mine_left, "my_open_spots": mine_spots, "league_budget_left": league_left,
            "league_spots_left": league_spots, "teams": teams}


PLAN = {"market": {"Star": 60, "Fit": 25, "Mid": 12, "Cheap": 2},
        "mine": {"Star": 30, "Fit": 35, "Mid": 12, "Cheap": 2}, "max_bid": 90}


def _texts(items, kind=None):
    return [i["text"] for i in items if kind is None or i["kind"] == kind]


def test_you_are_told_how_your_cash_compares_with_the_league():
    rich = advice.cash_advice(PLAN, _state(mine_left=200, mine_spots=5, league_left=600, league_spots=30))
    assert "outspend" in _texts(rich, "cash")[0] and "$200 for 5 open spots" in _texts(rich, "cash")[0]
    poor = advice.cash_advice(PLAN, _state(mine_left=40, mine_spots=5, league_left=600, league_spots=30))
    assert "less to spend" in _texts(poor, "cash")[0]
    even = advice.cash_advice(PLAN, _state(mine_left=100, mine_spots=5, league_left=600, league_spots=30))
    assert "about even" in _texts(even, "cash")[0]


def test_a_full_roster_says_so():
    assert "roster is full" in _texts(advice.cash_advice(PLAN, _state(mine_left=0, mine_spots=0)))[0]


def test_without_rivals_only_your_own_money_is_covered():
    items = advice.cash_advice(PLAN, _state(rivals=[]))
    assert [i["kind"] for i in items] == ["cash"]


def test_rival_cash_is_tracked_including_teams_that_are_nearly_out():
    rivals = [_team("Rich Team", 150, 8), _team("Broke Team", 6, 5), _team("Mid Team", 80, 6)]
    items = advice.cash_advice(PLAN, _state(rivals=rivals))
    text = " ".join(_texts(items, "rivals"))
    assert "Rich Team has the most cash left: $150 for 8 spots" in text
    assert "Broke Team can hardly bid" in text and "Mid Team can hardly" not in text


def test_nominate_the_player_who_is_worth_more_to_you_than_the_room_will_pay():
    # Only one rival can pay $25 for "Fit", but you value him at $35
    rivals = [_team("A", 40, 8), _team("B", 12, 6), _team("C", 10, 5)]
    items = advice.cash_advice(PLAN, _state(rivals=rivals))
    text = _texts(items, "nominate")[0]
    assert "Fit" in text and "worth $35 to you" in text and "only 1 of 3 rivals" in text


def test_nominate_an_overpriced_star_to_make_rivals_spend():
    rivals = [_team(n, 120, 8) for n in "ABCD"]
    items = advice.cash_advice(PLAN, _state(rivals=rivals))
    text = _texts(items, "drain")[0]
    assert "Star" in text and "worth only $30 to you" in text and "4 rivals can afford it" in text


def test_no_nomination_ideas_when_nothing_fits():
    plan = {"market": {"A": 5}, "mine": {"A": 5}, "max_bid": 50}
    assert not _texts(advice.cash_advice(plan, _state(rivals=[_team("A", 50, 5)])), "nominate")


# --- through the page's state endpoint ---------------------------------------------

def test_the_state_includes_cash_advice_in_auctions_only(env):  # noqa: F811
    env.monkeypatch.setattr(env.tracker, "auction", True)
    data = env.client.get("/draft/L1/state").get_json()
    assert data["cash_advice"] and data["cash_advice"][0]["kind"] == "cash"
    env.monkeypatch.setattr(env.tracker, "auction", False)
    assert "cash_advice" not in env.client.get("/draft/L1/state").get_json()


def _two_players(env):  # noqa: F811
    first, second = _top_names(env, 2)
    env.monkeypatch.setattr(env.tracker, "picks", [(first, 0, 30), (second, 0, 20)])
    return first, second


def test_a_punt_idea_appears_once_players_are_picked_and_changes_nothing_by_itself(env):  # noqa: F811
    assert env.client.get("/draft/L1/state").get_json()["build_suggestion"] is None
    _two_players(env)
    data = env.client.get("/draft/L1/state").get_json()
    idea = data["build_suggestion"]
    assert idea is not None and idea["category"] in data["categories"]
    assert data["punts"] == [] and data["effective_punts"] == [] and data["auto_punts"] is False


def test_auto_punts_apply_the_idea_and_rerank_the_recommendations(env):  # noqa: F811
    _two_players(env)
    plain = env.client.get("/draft/L1/state").get_json()
    idea = plain["build_suggestion"]["category"]
    auto = env.client.get("/draft/L1/state?auto_punts=1").get_json()
    assert auto["effective_punts"] == [idea] and auto["punts"] == [] and auto["auto_punts"] is True
    assert [r["name"] for r in auto["recommendations"]] != [r["name"] for r in plain["recommendations"]]
    # what the idea promised is what the list now shows
    assert [r["name"] for r in auto["recommendations"][:3]] == plain["build_suggestion"]["if_skipped"]


def test_a_skip_you_chose_yourself_is_respected_and_no_second_one_is_added(env):  # noqa: F811
    _two_players(env)
    data = env.client.get("/draft/L1/state?punts=FT%25&auto_punts=1").get_json()
    assert data["punts"] == ["FT%"] and data["effective_punts"] == ["FT%"]
    assert data["build_suggestion"] is None
