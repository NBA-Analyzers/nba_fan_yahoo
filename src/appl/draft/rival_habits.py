"""
How each team has spent so far in an auction, learned from the sales.

Every sale is compared with the market price the player had at that moment
(ranker.market_at_each_pick), overall and by position group. A team that keeps
paying well over (or under) market for one group has a habit, and the nominee
card warns when the player on the block is in that group.
"""

GROUPS = {"guards": {"PG", "SG", "G"}, "forwards": {"SF", "PF", "F"}, "centers": {"C"}}
MIN_BUYS = 2           # buys in a group before a pattern counts as a habit
HABIT_PREMIUM = 20     # % over or under market that is worth pointing out
HABIT_DOLLARS = 5      # ...and in real money, so $3 for two $1 players isn't a habit


def position_groups(eligible) -> set[str]:
    """Guards / forwards / centers a player belongs to (a PF/C is in two)."""
    return {g for g, spots in GROUPS.items() if eligible and eligible & spots}


def _premium(paid: int, market: int) -> int:
    return round((paid / market - 1) * 100) if market else 0


def team_habits(picks: list[dict], market_at_sale: list, lookup) -> dict:
    """team_key -> {"buys", "premium_pct", "habits"} from the priced sales.
    `market_at_sale` lines up with `picks`; `lookup(name)` gives eligible positions.
    Sales with no price (keepers, $0, players not in the pool) are skipped."""
    totals = {}
    for pick, market in zip(picks, market_at_sale):
        if not pick.get("cost") or not market:
            continue
        team = totals.setdefault(pick["team_key"], {"paid": 0, "market": 0, "buys": 0, "groups": {}})
        buckets = [team] + [
            team["groups"].setdefault(g, {"paid": 0, "market": 0, "buys": 0})
            for g in sorted(position_groups(lookup(pick["player_name"])))
        ]
        for bucket in buckets:
            bucket["paid"] += pick["cost"]
            bucket["market"] += market
            bucket["buys"] += 1

    result = {}
    for key, team in totals.items():
        habits = []
        for group, g in team["groups"].items():
            premium, overpay = _premium(g["paid"], g["market"]), g["paid"] - g["market"]
            if g["buys"] >= MIN_BUYS and abs(premium) >= HABIT_PREMIUM and abs(overpay) >= HABIT_DOLLARS:
                habits.append({"group": group, "buys": g["buys"], "premium_pct": premium, "overpay": overpay})
        result[key] = {
            "buys": team["buys"],
            "premium_pct": _premium(team["paid"], team["market"]),
            "habits": sorted(habits, key=lambda h: -abs(h["premium_pct"])),
        }
    return result


def habits_for(eligible, market: int, teams: list[dict]) -> list[dict]:
    """Rivals with a habit for the nominee's position group, and what that habit
    says they may pay for him (never more than they can bid), highest first."""
    groups = position_groups(eligible)
    found = []
    for team in teams:
        if team["is_mine"] or team["spots_left"] <= 0:
            continue
        matching = [h for h in team.get("habits", []) if h["group"] in groups]
        if not matching:
            continue
        habit = max(matching, key=lambda h: h["premium_pct"])
        found.append({
            "name": team["name"],
            **habit,
            "may_pay": min(max(round(market * (1 + habit["premium_pct"] / 100)), 1), team["max_bid"]),
        })
    return sorted(found, key=lambda r: -r["may_pay"])
