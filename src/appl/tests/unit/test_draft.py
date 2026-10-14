import random

import pytest

from appl.draft import jev_chooser
from appl.draft.player_pool import blend_seasons, normalize_name
from appl.draft.ranker import DraftRanker, categories_from_yahoo
from appl.draft.yahoo_draft import _extract_players, _flatten_player, next_snake_pick


def _name(prefix, i):
    # Letters only: normalize_name drops digits, which would merge "Big 1" and "Big 2"
    return f"{prefix} {chr(65 + i // 26)}{chr(97 + i % 26)}"


def _player(name, big, i, gp=None):
    rnd = random.Random(i)
    fga = rnd.uniform(8, 18)
    fta = rnd.uniform(5, 8) if big else rnd.uniform(1, 5)
    fgp = rnd.uniform(0.5, 0.62) if big else rnd.uniform(0.42, 0.48)
    ftp = rnd.uniform(0.5, 0.65) if big else rnd.uniform(0.8, 0.92)
    return {
        "nba_id": i, "name": name, "team": "XXX",
        "GP": gp if gp is not None else rnd.randint(50, 78),
        "MIN": rnd.uniform(22, 36), "PTS": rnd.uniform(10, 26),
        "REB": rnd.uniform(8, 13) if big else rnd.uniform(2, 6),
        "AST": rnd.uniform(1, 4) if big else rnd.uniform(3, 9),
        "STL": rnd.uniform(0.4, 1.6),
        "BLK": rnd.uniform(1, 2.5) if big else rnd.uniform(0.1, 0.5),
        "TOV": rnd.uniform(1, 3.5),
        "FG3M": rnd.uniform(0, 0.5) if big else rnd.uniform(1, 3.5),
        "FGM": fga * fgp, "FGA": fga, "FTM": fta * ftp, "FTA": fta,
    }


@pytest.fixture(scope="module")
def pool():
    players = [_player(_name("Big", i), True, i) for i in range(80)]
    players += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    players.append(_player("Rookie", False, 999, gp=4))
    players.append(_player("Nicolas Claxton", True, 998))
    return players


@pytest.fixture(scope="module")
def ranker(pool):
    return DraftRanker(pool, num_teams=12, roster_size=13)


def _bigs(recs):
    return sum(r["name"].startswith("Big") for r in recs)


# --- player pool -------------------------------------------------------------

def test_normalize_name_handles_accents_suffixes_and_punctuation():
    assert normalize_name("Nikola Jokić") == "nikola jokic"
    assert normalize_name("Kelly Oubre Jr.") == "kelly oubre"
    assert normalize_name("P.J. Washington") == "pj washington"
    assert normalize_name("Karl-Anthony Towns") == "karl anthony towns"


def _line(gp, pts):
    return {"name": "A", "team": "T", "GP": gp, "MIN": 30, "PTS": pts, "REB": 5,
            "AST": 5, "STL": 1, "BLK": 1, "TOV": 2, "FG3M": 1, "FGM": 5,
            "FGA": 10, "FTM": 3, "FTA": 4}


def test_blend_weights_seasons_and_uses_single_season_when_alone():
    pool = blend_seasons(
        [({1: _line(70, 20), 2: _line(10, 30)}, 0.7), ({1: _line(70, 10)}, 0.3)]
    )
    by_id = {p["nba_id"]: p for p in pool}
    assert by_id[1]["PTS"] == pytest.approx(17.0)
    assert by_id[2]["PTS"] == pytest.approx(30.0)


def test_blend_discounts_small_samples():
    # 10 recent games should count for less than a full 70-game old season
    pool = blend_seasons([({1: _line(10, 30)}, 0.7), ({1: _line(70, 10)}, 0.3)])
    assert pool[0]["PTS"] < 0.7 * 30 + 0.3 * 10


# --- ranker ------------------------------------------------------------------

def test_players_under_min_games_are_excluded(ranker):
    assert ranker.find("Rookie") is None


def test_punting_changes_the_build(ranker):
    base = _bigs(ranker.rank(limit=25))
    assert _bigs(ranker.rank(punts=["FT%"], limit=25)) > base
    assert _bigs(ranker.rank(punts=["AST"], limit=25)) > base


def test_punted_categories_do_not_affect_score(ranker):
    recs = ranker.rank(punts=["FT%"], limit=5)
    for rec in recs:
        expected = sum(v for c, v in rec["z"].items() if c != "FT%")
        assert rec["punt_value"] == pytest.approx(expected, abs=0.02)


def test_taken_players_are_removed(ranker):
    first = ranker.rank(limit=1)[0]["name"]
    assert first not in [r["name"] for r in ranker.rank(taken_names=[first], limit=300)]


def test_fuzzy_matching_catches_close_spellings(ranker):
    # One letter off: not an exact match after normalizing, so this takes the fuzzy path
    assert normalize_name("Nicolas Claxon") not in {p["key"] for p in ranker.players}
    assert ranker.find("Nicolas Claxon")["name"] == "Nicolas Claxton"
    assert ranker.unmatched(["Totally Unknown Person"]) == ["Totally Unknown Person"]
    taken = ["Nicolas Claxon"]
    assert "Nicolas Claxton" not in [
        r["name"] for r in ranker.rank(taken_names=taken, limit=300)
    ]


def test_keys_are_unique_per_player(ranker):
    assert len({p["key"] for p in ranker.players}) == len(ranker.players)


def test_taken_removes_only_that_player(ranker):
    before = {r["name"] for r in ranker.rank(limit=300)}
    first = ranker.rank(limit=1)[0]["name"]
    after = {r["name"] for r in ranker.rank(taken_names=[first], limit=300)}
    assert before - after == {first}


def test_suggested_punts_need_a_few_players(ranker):
    roster = [r["name"] for r in ranker.rank(punts=["AST"], limit=4)]
    assert ranker.suggest_punts(roster[:2]) == []
    assert len(ranker.suggest_punts(roster)) == 2


def test_need_weighting_prefers_covering_weak_categories(ranker):
    bigs = [r["name"] for r in ranker.rank(punts=["AST", "3PTM"], limit=4)]
    with_roster = ranker.rank(my_roster_names=bigs, limit=25)
    without = ranker.rank(limit=25)
    assert [r["name"] for r in with_roster] != [r["name"] for r in without]


def test_auction_values_roughly_spend_the_budget(ranker):
    bids = ranker.auction_values(budget=2400, spots=156)
    assert len(bids) == 156
    assert min(bids.values()) >= 1
    assert abs(sum(bids.values()) - 2400) < 60


def test_categories_from_yahoo_maps_names_and_falls_back():
    cats = categories_from_yahoo(
        [{"display_name": "ST"}, {"display_name": "FG%"}, {"display_name": "Weird"}]
    )
    assert cats == ["STL", "FG%"]
    assert len(categories_from_yahoo([])) == 9


# --- yahoo tracker -----------------------------------------------------------

def test_next_snake_pick():
    assert next_snake_pick(14, 12, 3) == 22
    assert next_snake_pick(0, 12, 3) == 3
    assert next_snake_pick(12, 12, 12) == 13
    assert next_snake_pick(5, 12, None) is None


def test_yahoo_player_payload_parsing():
    raw = {"fantasy_content": {"league": [{}, {"players": {"0": {"player": [
        [{"player_key": "428.p.1"}, {"name": {"full": "Nikola Jokic"}}],
        {"draft_analysis": [{"average_pick": "1.4"}, {"average_round": "1.0"}]},
    ]}, "count": 1}}]}}
    players = _extract_players(raw)
    assert players[0]["name"]["full"] == "Nikola Jokic"
    assert _flatten_player(players[0]["draft_analysis"])["average_pick"] == "1.4"
    assert _extract_players({}) == []


# --- jev chooser -------------------------------------------------------------

class _Answer:
    def __init__(self, choice, confidence, probabilities):
        self.choice, self.confidence, self.probabilities = choice, confidence, probabilities


class _FakeJev:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.requests = answer, fail, []

    def system_one(self, state, questions):
        self.requests.append((state, questions))
        if self.fail:
            raise RuntimeError("down")
        return type("R", (), {"choices": {"pick": self.answer}})()


def _decide(ranker, mode, client, roster=(), punts=("AST",), preference=""):
    recs = ranker.rank(punts=list(punts), limit=25)
    return recs, jev_chooser.decide(
        mode, recs, list(roster), list(punts), ranker.categories,
        ranker.roster_profile(list(roster)), preference, client=client,
    )


def test_request_omits_punted_categories_and_labels_scores(ranker):
    recs = ranker.rank(punts=["AST"], limit=25)
    state, criteria = jev_chooser.build_request(
        recs, [], ["AST"], ranker.categories, ranker.roster_profile([]), "a big man"
    )
    assert state["punted_categories"] == ["AST"]
    assert state["manager_preference"] == "a big man"
    assert len(criteria) == 25
    one = next(iter(criteria.values()))
    assert "AST" not in one["category_z"]
    assert one["category_z"]["REB"][0] in "+-"


def test_manual_mode_never_calls_jev(ranker):
    client = _FakeJev(_Answer("x", 1.0, {"x": 1.0}))
    _, decision = _decide(ranker, "manual", client)
    assert decision is None and client.requests == []


def test_assist_mode_always_leaves_the_decision_to_the_manager(ranker):
    recs = ranker.rank(punts=["AST"], limit=25)
    name = recs[2]["name"]
    _, decision = _decide(ranker, "assist", _FakeJev(_Answer(name, 0.95, {name: 0.95})))
    assert decision["pick"] == name and decision["needs_manager"] is True
    assert decision["agrees_with_engine"] is False


def test_auto_mode_respects_the_confidence_threshold(ranker):
    recs = ranker.rank(punts=["AST"], limit=25)
    a, b = recs[1]["name"], recs[0]["name"]
    _, sure = _decide(ranker, "auto", _FakeJev(_Answer(a, 0.9, {a: 0.9, b: 0.1})))
    _, unsure = _decide(ranker, "auto", _FakeJev(_Answer(a, 0.3, {a: 0.3, b: 0.25})))
    assert sure["needs_manager"] is False
    assert unsure["needs_manager"] is True and "you decide" in unsure["note"]
    assert len(unsure["options"]) == 2


def test_failure_or_unknown_pick_falls_back_to_the_engine(ranker):
    recs, failed = _decide(ranker, "auto", _FakeJev(fail=True))
    assert failed["source"] == "engine" and failed["pick"] == recs[0]["name"]
    _, bogus = _decide(ranker, "auto", _FakeJev(_Answer("Nobody", 1.0, {"Nobody": 1.0})))
    assert bogus["source"] == "engine"


def test_explanation_names_strengths_in_original_case(ranker):
    rec = ranker.rank(limit=1)[0]
    text = jev_chooser.explain(rec, {c: 0.0 for c in ranker.categories}, [], False)
    assert text.endswith(".") and text[0].isupper()
    if rec["strengths"]:
        assert rec["strengths"][0] in text


# --- mock draft harness ------------------------------------------------------

def test_mock_draft_fills_every_roster_with_distinct_players():
    from appl.draft import mock_eval

    r = DraftRanker(mock_eval.synthetic_pool(), num_teams=12)
    draft = mock_eval.run_draft(r, "ranker", ["FT%"], seat=4, seed=1)
    everyone = [name for team in draft["teams"] for name in team]
    assert all(len(team) == 13 for team in draft["teams"])
    assert len(everyone) == len(set(everyone)) == 12 * 13

    result = mock_eval.evaluate(r, draft["teams"], 4, ["FT%"])
    assert 0 <= result["win_pct_all"] <= 1 and set(result["wins"]) == set(r.categories)


def test_mock_draft_jev_strategy_uses_the_chooser_and_counts_fallbacks():
    from appl.draft import mock_eval

    r = DraftRanker(mock_eval.synthetic_pool(), num_teams=12)

    class AlwaysSecond(_FakeJev):
        def system_one(self, state, questions):
            names = list(questions["pick"].criteria)
            self.answer = _Answer(names[1], 0.8, {names[1]: 0.8, names[0]: 0.2})
            return super().system_one(state, questions)

    draft = mock_eval.run_draft(r, "jev", ["FT%"], seat=0, seed=2, jev_client=AlwaysSecond())
    assert draft["stats"]["jev_calls"] == 13 and draft["stats"]["jev_agrees"] == 0
    failed = mock_eval.run_draft(r, "jev", ["FT%"], seat=0, seed=2, jev_client=_FakeJev(fail=True))
    assert failed["stats"]["jev_fallbacks"] == 13


# --- ESPN stats source -------------------------------------------------------

def _espn_payload():
    names = {
        "general": ["gamesPlayed", "avgMinutes", "avgRebounds"],
        "offensive": ["avgPoints", "avgFieldGoalsMade", "avgFieldGoalsAttempted",
                      "avgThreePointFieldGoalsMade", "avgFreeThrowsMade",
                      "avgFreeThrowsAttempted", "avgAssists", "avgTurnovers"],
        "defensive": ["avgSteals", "avgBlocks"],
    }
    full = [
        {"name": "general", "values": [64.0, 35.8, 7.7]},
        {"name": "offensive", "values": [33.5, 10.8, 22.8, 4.0, 7.9, 10.1, 8.3, 4.0]},
        {"name": "defensive", "values": [1.6, 0.5]},
    ]
    return {
        "categories": [{"name": n, "names": v} for n, v in names.items()],
        "athletes": [
            {"athlete": {"id": "3945274", "displayName": "Luka Doncic", "teamShortName": "LAL"},
             "categories": full},
            # missing the defensive category entirely: must be skipped, not crash
            {"athlete": {"id": "1", "displayName": "Incomplete Player"}, "categories": full[:2]},
        ],
    }


def test_espn_rows_become_per_game_lines_and_incomplete_rows_are_skipped():
    from appl.draft.player_pool import parse_espn_athletes

    players = parse_espn_athletes(_espn_payload())
    assert list(players) == [3945274]
    luka = players[3945274]
    assert luka["name"] == "Luka Doncic" and luka["team"] == "LAL"
    assert (luka["GP"], luka["PTS"], luka["REB"], luka["AST"]) == (64.0, 33.5, 7.7, 8.3)
    assert (luka["FG3M"], luka["FTM"], luka["FTA"], luka["STL"], luka["BLK"]) == (4.0, 7.9, 10.1, 1.6, 0.5)


def test_espn_season_label_uses_the_ending_year():
    from appl.draft.player_pool import _espn_season_year

    assert _espn_season_year("2025-26") == 2026 and _espn_season_year("2024-25") == 2025


def test_fetch_falls_back_to_nba_api_when_espn_fails(monkeypatch):
    from appl.draft import player_pool

    def boom(season):
        raise RuntimeError("espn down")

    monkeypatch.setattr(player_pool, "_fetch_season_espn", boom)
    monkeypatch.setattr(player_pool, "_fetch_season_nba_api", lambda season: {7: {"name": "X"}})
    assert player_pool._fetch_season("2025-26") == {7: {"name": "X"}}


# --- positions ---------------------------------------------------------------

def test_required_slots_ignores_bench_and_injured_list():
    from appl.draft.positions import required_slots

    slots = required_slots({"PG": {"count": 1}, "C": {"count": "1"}, "Util": {"count": 3},
                            "BN": {"count": 3}, "IL": {"count": 1}, "IL+": {"count": 1}})
    assert slots == {"PG": 1, "C": 1, "Util": 3}


def test_parse_eligible_accepts_both_yahoo_shapes():
    from appl.draft.positions import parse_eligible

    assert parse_eligible(["PG", "G", "Util"]) == {"PG", "G", "Util"}
    assert parse_eligible([{"position": "C"}, {"position": "Util"}]) == {"C", "Util"}
    assert parse_eligible(None) == set()


def test_assignment_uses_matching_not_first_fit():
    from appl.draft.positions import assign

    # The PG/SG player must take SG so the PG-only player can start at PG
    started, empty = assign([{"PG", "SG"}, {"PG"}], {"PG": 1, "SG": 1, "C": 1})
    assert started == 2 and empty == ["C"]


def test_flex_slot_takes_anyone_and_reports_specific_slots_first():
    from appl.draft.positions import assign, roster_report

    started, empty = assign([{"PG"}, {"PG"}, {"PG"}], {"PG": 1, "C": 1, "Util": 2})
    assert started == 3 and empty == ["C"]
    report = roster_report([{"PG"}], {"PG": 1, "C": 1, "Util": 1}, nominee={"C"})
    assert report["fills_open_slot"] is True and report["still_empty_after"] == ["Util"]
    assert roster_report([{"PG"}, {"C"}], {"PG": 1, "C": 1}, nominee={"PG"})["fills_open_slot"] is False


# --- auction plan ------------------------------------------------------------

def _plan(ranker, **kw):
    args = dict(punts=[], taken_names=[], my_roster_names=[], league_budget_left=2400,
                league_budget_total=2400, league_spots_left=156, my_budget_left=200,
                my_open_spots=13)
    args.update(kw)
    return ranker.auction_plan(**args)


def test_plan_at_the_start_has_no_inflation_and_a_safe_max_bid(ranker):
    plan = _plan(ranker)
    assert plan["inflation_pct"] == 0.0 and plan["max_bid"] == 187


def test_max_bid_keeps_a_dollar_for_every_open_spot(ranker):
    assert _plan(ranker, my_budget_left=10, my_open_spots=5)["max_bid"] == 5
    assert _plan(ranker, my_budget_left=10, my_open_spots=0)["max_bid"] == 0


def test_my_price_follows_my_punts_while_the_market_does_not(ranker):
    plain, punting = _plan(ranker), _plan(ranker, punts=["FT%", "AST"])
    assert plain["market"] == punting["market"]
    assert plain["mine"] != punting["mine"]
    # The big with the worst FT% is worth more to a build that punts FT%
    worst_ft = min((p for p in ranker.players if p["name"].startswith("Big")), key=lambda p: p["z"]["FT%"])
    assert punting["mine"][worst_ft["name"]] >= plain["mine"][worst_ft["name"]]


def test_prices_rise_when_stars_sell_below_value(ranker):
    stars = [r["name"] for r in ranker.rank(limit=3)]
    after = _plan(ranker, taken_names=stars, league_budget_left=2400 - 3, league_spots_left=153)
    assert after["inflation_pct"] > 0


def test_sold_players_leave_the_price_tables(ranker):
    star = ranker.rank(limit=1)[0]["name"]
    plan = _plan(ranker, taken_names=[star], league_spots_left=155)
    assert star not in plan["market"] and star not in plan["mine"]
