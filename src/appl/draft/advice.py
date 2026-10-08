"""
Plain-language advice while the draft is running.

build_suggestion  - once a few players are on your team, which one category to skip
                    and how the best available players change if you do.
cash_advice       - auctions: how your money compares, who can still pay, and who to
                    nominate (to get a player cheaply, or to make rivals spend).

Mock drafts showed that skipping one category helps but skipping two usually hurts,
so only one is ever suggested, and only while none is skipped yet.
"""

MIN_PLAYERS_FOR_PUNT = 2
WEAK_AVG_Z = -0.4  # a category is "clearly weak" when your players average below this
RICH = 1.15  # you can outspend the league when your cash per open spot is this much higher
POOR = 0.85
BROKE_MAX_BID = 3  # a rival who can bid no more than this is effectively out
STAR_POOL = 40  # nomination ideas come from the 40 players the room values most


def build_suggestion(ranker, roster: list[str], punts: list[str], taken: list[str]) -> dict | None:
    """The weakest category on your team and what skipping it would do. None when you
    have too few players, already skip something, or nothing is clearly weak."""
    if punts or len([n for n in roster if ranker.find(n)]) < MIN_PLAYERS_FOR_PUNT:
        return None
    profile = ranker.roster_profile(roster)
    category = min(profile, key=profile.get)
    if profile[category] > WEAK_AVG_Z:
        return None

    def best(skip: list[str]) -> list[str]:
        recs = ranker.rank(punts=skip, taken_names=taken, my_roster_names=roster, limit=3)
        return [r["name"] for r in recs]

    return {
        "category": category,
        "avg_z": profile[category],
        "now": best([]),
        "if_skipped": best([category]),
    }


def cash_advice(plan: dict, state: dict) -> list[dict]:
    """Auction advice from the money left. Each item is {"kind", "text"}."""
    advice = []
    budget, open_spots = state["my_budget_left"], state["my_open_spots"]
    league_budget, league_spots = state["league_budget_left"], state["league_spots_left"]

    if open_spots > 0 and league_spots > 0:
        mine_each, league_each = budget / open_spots, league_budget / league_spots
        text = (f"You have ${budget} for {open_spots} open spots (${mine_each:.0f} a spot). "
                f"The league average is ${league_each:.0f} a spot.")
        if mine_each >= RICH * league_each:
            text += " You can outspend most teams on the players you really want."
        elif mine_each <= POOR * league_each:
            text += " You have less to spend than most teams, so chase players who fit your team and let the stars go."
        else:
            text += " That is about even with the other teams."
        advice.append({"kind": "cash", "text": text})
    elif open_spots == 0:
        advice.append({"kind": "cash", "text": "Your roster is full. You can't bid on anyone else."})

    rivals = [t for t in state.get("teams", []) if not t["is_mine"]]
    if not rivals:
        return advice

    richest = max(rivals, key=lambda t: t["budget_left"])
    advice.append({"kind": "rivals", "text": f"{richest['name']} has the most cash left: ${richest['budget_left']} for {richest['spots_left']} spots."})
    broke = [t for t in rivals if t["spots_left"] > 0 and t["max_bid"] <= BROKE_MAX_BID]
    if broke:
        names = ", ".join(t["name"] for t in broke[:4])
        advice.append({"kind": "rivals", "text": f"{names} can hardly bid any more (max ${max(t['max_bid'] for t in broke)}). They won't push prices up."})

    market, mine = plan["market"], plan["mine"]
    stars = sorted(market, key=market.get, reverse=True)[:STAR_POOL]

    def buyers(name: str) -> int:
        return sum(t["max_bid"] >= market[name] for t in rivals)

    # A player who is worth more to you than the room will pay, and few rivals can afford
    gets = [(mine[n] - market[n], n) for n in stars
            if mine[n] >= max(market[n], 2) and mine[n] <= plan["max_bid"] and buyers(n) <= len(rivals) / 2]
    if gets:
        _, name = max(gets)
        advice.append({"kind": "nominate", "text": f"Good one to nominate for yourself: {name}. He is worth ${mine[name]} to you, and only {buyers(name)} of {len(rivals)} rivals can pay about ${market[name]}."})

    # A player the room will pay a lot for but who doesn't fit you: let rivals burn cash
    drains = [(market[n], n) for n in stars
              if market[n] >= 10 and mine[n] < 0.8 * market[n] and buyers(n) >= 3]
    if drains:
        price, name = max(drains)
        advice.append({"kind": "drain", "text": f"To make rivals spend: nominate {name}. He is worth only ${mine[name]} to you, but the room will pay about ${price} and {buyers(name)} rivals can afford it."})
    return advice
