from appl.draft import rival_habits
from appl.draft.ranker import DraftRanker
from appl.tests.unit.test_draft import _name, _player

GUARD, CENTER = {"PG", "G", "Util"}, {"C", "Util"}


def _pick(team, name, cost):
    return {"team_key": team, "team_name": f"Team {team}", "player_name": name, "cost": cost}


def _lookup(table):
    return lambda name: table.get(name)


def test_position_groups_cover_combo_players():
    assert rival_habits.position_groups({"PG", "SG", "G", "Util"}) == {"guards"}
    assert rival_habits.position_groups({"PF", "C", "F", "Util"}) == {"forwards", "centers"}
    assert rival_habits.position_groups({"Util"}) == set()
    assert rival_habits.position_groups(None) == set()


def test_a_team_that_keeps_overpaying_for_guards_gets_a_habit():
    picks = [_pick("t3", "G1", 30), _pick("t3", "G2", 15), _pick("t3", "C1", 20)]
    habits = rival_habits.team_habits(picks, [20, 10, 20], _lookup({"G1": GUARD, "G2": GUARD, "C1": CENTER}))
    t3 = habits["t3"]
    assert t3["buys"] == 3 and t3["premium_pct"] == 30
    assert t3["habits"] == [{"group": "guards", "buys": 2, "premium_pct": 50, "overpay": 15}]


def test_one_buy_or_a_few_dollars_is_not_a_habit():
    lookup = _lookup({"G1": GUARD, "G2": GUARD, "G3": GUARD})
    one = rival_habits.team_habits([_pick("t1", "G1", 40)], [20], lookup)
    assert one["t1"]["habits"] == []
    # $3 for two $1 players is +200%, but only $4 over: noise, not a habit
    cheap = rival_habits.team_habits([_pick("t1", "G2", 3), _pick("t1", "G3", 3)], [1, 1], lookup)
    assert cheap["t1"]["habits"] == []


def test_bargain_hunting_is_a_habit_too():
    lookup = _lookup({"C1": CENTER, "C2": CENTER})
    habits = rival_habits.team_habits([_pick("t2", "C1", 14), _pick("t2", "C2", 10)], [20, 20], lookup)
    assert habits["t2"]["habits"] == [{"group": "centers", "buys": 2, "premium_pct": -40, "overpay": -16}]


def test_free_or_unpriced_sales_are_skipped():
    habits = rival_habits.team_habits(
        [_pick("t1", "Keeper", 0), _pick("t1", "Ghost", 12), _pick("t1", "G1", None)],
        [25, None, 10], _lookup({"Keeper": GUARD, "G1": GUARD}),
    )
    assert habits == {}


def _rival(key, max_bid=100, spots=5, habits=()):
    return {"team_key": key, "name": f"Team {key}", "max_bid": max_bid, "spots_left": spots,
            "is_mine": False, "habits": list(habits)}


def test_nominee_warning_names_rivals_with_a_matching_habit():
    over = {"group": "centers", "buys": 3, "premium_pct": 50, "overpay": 24}
    under = {"group": "centers", "buys": 2, "premium_pct": -30, "overpay": -12}
    guards = {"group": "guards", "buys": 2, "premium_pct": 80, "overpay": 30}
    teams = [
        _rival("t1", habits=[over]),
        _rival("t2", max_bid=25, habits=[over]),          # capped at what they can bid
        _rival("t3", habits=[under]),
        _rival("t4", habits=[guards]),                     # habit for another group
        _rival("t5", spots=0, habits=[over]),              # roster full
        dict(_rival("t0", habits=[over]), is_mine=True),   # you
    ]
    found = rival_habits.habits_for(CENTER, 20, teams)
    assert [(r["name"], r["may_pay"]) for r in found] == [("Team t1", 30), ("Team t2", 25), ("Team t3", 14)]
    assert found[0]["group"] == "centers" and found[0]["premium_pct"] == 50


def test_nominee_without_known_positions_gets_no_warning():
    teams = [_rival("t1", habits=[{"group": "centers", "buys": 3, "premium_pct": 50, "overpay": 24}])]
    assert rival_habits.habits_for(None, 20, teams) == []


# --- replaying the market --------------------------------------------------

def _ranker():
    pool = [_player(_name("Big", i), True, i) for i in range(80)]
    pool += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    return DraftRanker(pool, num_teams=12, roster_size=13)


def _market(ranker, taken, money, spots):
    return ranker.auction_plan([], taken, [], money, 2400, spots, 200, 13)["market"]


def test_each_sale_is_priced_with_the_money_and_spots_left_at_that_moment():
    ranker = _ranker()
    first, second = [r["name"] for r in ranker.rank(limit=2)]
    prices = ranker.market_at_each_pick([(first, 70), (second, 5), ("Nobody Real", 3)], 2400)
    assert prices[0] == _market(ranker, [], 2400, 156)[first]
    assert prices[1] == _market(ranker, [first], 2400 - 70, 155)[second]
    assert prices[2] is None
