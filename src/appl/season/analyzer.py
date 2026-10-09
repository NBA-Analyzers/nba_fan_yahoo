"""
In-season analysis of one team against its league. Pure, no I/O.

Each team's per-game production is summed over its roster (percentages from
total makes and attempts), every category is ranked across the league, and the
team's roto points are the sum of those ranks. Moves are judged by what they do
to those points:

  pickups  - free agents worth adding, each paired with the drop that helps most
  trades   - 1-for-1 and 2-for-1 deals that raise your points while the other
             team gets fair value by its own needs (so it might say yes)
  drops    - your players who add least to the categories you count
"""

from statistics import pstdev

from ..draft.ranker import COUNTING_STATS, NEGATIVE_CATEGORIES, PERCENT_STATS

STATS = ("FGM", "FGA", "FTM", "FTA", "FG3M", "PTS", "REB", "AST", "STL", "BLK", "TOV")
_IDX = {s: i for i, s in enumerate(STATS)}
ZERO = tuple(0.0 for _ in STATS)

CLOSE_GAP_SD = 0.25  # passing the next team takes under a quarter of the league's spread
FAR_GAP_SD = 1.0
FAIR_MARGIN = 0.75  # the other team may lose at most this much value (z) by its own needs
TRADE_PARTNER_PLAYERS = 10  # look at each rival's best players only
TRADES_PER_PARTNER = 2
MAX_TRADES = 5
MIN_OTHER_SHAPE = 2  # trade slots kept for the less common deal shape
MAX_PICKUPS = 8
FREE_AGENT_POOL = 25
MAX_DROPS = 3


def _line(player: dict) -> tuple:
    return tuple(float(player.get(s, 0) or 0) for s in STATS)


def _add(a: tuple, b: tuple, sign: int = 1) -> tuple:
    return tuple(x + sign * y for x, y in zip(a, b))


def _sum(lines) -> tuple:
    total = ZERO
    for line in lines:
        total = _add(total, line)
    return total


def category_value(totals: tuple, category: str) -> float:
    if category in PERCENT_STATS:
        made, attempts = PERCENT_STATS[category]
        att = totals[_IDX[attempts]]
        return totals[_IDX[made]] / att if att else 0.0
    return totals[_IDX[COUNTING_STATS[category]]]


def _round(value: float, category: str) -> float:
    return round(value, 3 if category in PERCENT_STATS else 1)


def _better(category: str, a: float, b: float) -> bool:
    return a < b if category in NEGATIVE_CATEGORIES else a > b


def _ranks(values: list[float], category: str) -> list[int]:
    """1 = best. Ties share the better rank."""
    return [1 + sum(_better(category, other, v) for other in values) for v in values]


def _points(team_totals: list[tuple], categories: list[str]) -> list[int]:
    """Roto points per team over `categories` (n points for first, 1 for last)."""
    n = len(team_totals)
    points = [0] * n
    for c in categories:
        for i, rank in enumerate(_ranks([category_value(t, c) for t in team_totals], c)):
            points[i] += n - rank + 1
    return points


class SeasonAnalyzer:
    def __init__(self, ranker, snapshot, punts: list[str] | None = None):
        self.ranker = ranker
        self.snapshot = snapshot
        self.categories = [c for c in snapshot.categories if c in ranker.categories] or ranker.categories
        self.punts = [p for p in (punts or []) if p in self.categories]
        self.counted = [c for c in self.categories if c not in self.punts]
        self.me = snapshot.my_team

        self.players: list[list[dict]] = []
        self.unmatched: list[str] = []
        for roster in snapshot.rosters:
            found = []
            for name in roster:
                player = ranker.find(name)
                if player:
                    found.append(player)
                else:
                    self.unmatched.append(name)
            self.players.append(found)
        self.totals = [_sum(_line(p) for p in team) for team in self.players]
        self._values = {c: [category_value(t, c) for t in self.totals] for c in self.categories}
        # Your weights honor your punts; rivals' punts are unknown
        self._weights = {
            team: ranker._need_weights(self._names(team), set(self.punts if team == self.me else []))
            for team in range(len(self.players))
        }
        self._fits: dict[tuple, float] = {}

    # --- helpers ------------------------------------------------------------

    def _team_name(self, team: int) -> str:
        names = self.snapshot.team_names
        return names[team] if team < len(names) and names[team] else f"Team {team + 1}"

    def _names(self, team: int) -> list[str]:
        return [p["name"] for p in self.players[team]]

    def _value(self, team: int, player: dict) -> float:
        """What a player is worth to `team`, by that team's needs (and your punts)."""
        key = (team, player["key"])
        if key not in self._fits:
            self._fits[key] = self.ranker._fit(player, self._weights[team])
        return self._fits[key]

    def _my_points(self, changes: dict[int, tuple] | None = None) -> int:
        """My roto points over the counted categories, with some teams' totals
        replaced. Only my rank is needed, which keeps the trade search fast."""
        changes = changes or {}
        n = len(self.totals)
        mine_totals = changes.get(self.me, self.totals[self.me])
        points = 0
        for c in self.counted:
            values = self._values[c]
            mine = category_value(mine_totals, c)
            better = sum(
                _better(c, category_value(changes[i], c) if i in changes else values[i], mine)
                for i in range(n)
                if i != self.me
            )
            points += n - better
        return points

    def _with(self, changes: dict[int, tuple]) -> list[tuple]:
        return [changes.get(i, t) for i, t in enumerate(self.totals)]

    def _rank_changes(self, totals: list[tuple]) -> dict[str, int]:
        """Category -> places gained (+) or lost (-) for my team."""
        changes = {}
        for c in self.counted:
            before = _ranks(self._values[c], c)[self.me]
            after = _ranks([category_value(t, c) for t in totals], c)[self.me]
            if before != after:
                changes[c] = before - after
        return changes

    def _free_agents(self, limit: int = FREE_AGENT_POOL) -> list[dict]:
        recs = self.ranker.rank(
            punts=self.punts,
            taken_names=self.snapshot.rostered(),
            my_roster_names=self._names(self.me),
            limit=limit,
        )
        return [self.ranker.find(r["name"]) for r in recs]

    # --- standings ----------------------------------------------------------

    def standings(self) -> list[dict]:
        n = len(self.totals)
        ranks = {c: _ranks(self._values[c], c) for c in self.categories}
        points = _points(self.totals, self.counted)
        teams = [
            {
                "index": i,
                "name": self._team_name(i),
                "is_mine": i == self.me,
                "players": len(self.players[i]),
                "values": {c: _round(self._values[c][i], c) for c in self.categories},
                "ranks": {c: ranks[c][i] for c in self.categories},
                "points": points[i],
            }
            for i in range(n)
        ]
        for place, i in enumerate(sorted(range(n), key=lambda i: -points[i]), start=1):
            teams[i]["place"] = place
        return teams

    def my_categories(self) -> list[dict]:
        n = len(self.totals)
        third = max(1, round(n / 3))
        rows = []
        for c in self.categories:
            values = self._values[c]
            mine = values[self.me]
            spread = pstdev(values) or 1.0
            ahead = [abs(v - mine) for v in values if _better(c, v, mine)]
            behind = [abs(v - mine) for v in values if _better(c, mine, v)]
            gap_up = min(ahead) if ahead else None
            cushion = min(behind) if behind else None
            rank = 1 + len(ahead)
            rows.append({
                "category": c,
                "punted": c in self.punts,
                "rank": rank,
                "value": _round(mine, c),
                "label": "strong" if rank <= third else "weak" if rank > n - third else "middle",
                "gap_up": _round(gap_up, c) if gap_up is not None else None,
                "gap_up_sd": round(gap_up / spread, 2) if gap_up is not None else None,
                "cushion": _round(cushion, c) if cushion is not None else None,
                "cushion_sd": round(cushion / spread, 2) if cushion is not None else None,
            })
        return rows

    # --- moves --------------------------------------------------------------

    def pickups(self) -> list[dict]:
        """Free agents that raise your points, each with the drop that helps most."""
        base = self._my_points()
        found = []
        for fa in self._free_agents():
            best = None
            for drop in self.players[self.me]:
                changes = {self.me: _add(_add(self.totals[self.me], _line(drop), -1), _line(fa))}
                gain = self._my_points(changes) - base
                value = self._value(self.me, fa) - self._value(self.me, drop)
                if best is None or (gain, value) > best[:2]:
                    best = (gain, value, drop, changes)
            if best and (best[0] > 0 or (best[0] == 0 and best[1] > 0)):
                gain, value, drop, changes = best
                found.append({
                    "add": fa["name"],
                    "add_team": fa.get("team"),
                    "drop": drop["name"],
                    "points_gain": gain,
                    "value_gain": round(value, 2),
                    "category_changes": self._rank_changes(self._with(changes)),
                })
        found.sort(key=lambda m: (m["points_gain"], m["value_gain"]), reverse=True)
        return found[:MAX_PICKUPS]

    def drops(self) -> list[dict]:
        mine = sorted(self.players[self.me], key=lambda p: self._value(self.me, p))
        return [
            {
                "name": p["name"],
                "value": round(self._value(self.me, p), 2),
                "weak_in": [c for c in self.counted if p["z"][c] <= -1.0],
            }
            for p in mine[:MAX_DROPS]
        ]

    def trades(self) -> list[dict]:
        base = self._my_points()
        base_points = _points(self.totals, self.categories)
        mine = self.players[self.me]
        free_agent = next(iter(self._free_agents(limit=1)), None)
        offers = [[p] for p in mine] + [[a, b] for i, a in enumerate(mine) for b in mine[i + 1:]]
        ideas = []

        for partner in range(len(self.players)):
            if partner == self.me or not self.players[partner]:
                continue
            theirs = sorted(
                self.players[partner], key=lambda p: sum(p["z"][c] for c in self.categories), reverse=True
            )[:TRADE_PARTNER_PLAYERS]

            found = []
            for give in offers:
                give_line = _sum(map(_line, give))
                give_value = sum(self._value(partner, p) for p in give)
                for get in theirs:
                    their_value = give_value - self._value(partner, get)
                    my_totals = _add(_add(self.totals[self.me], give_line, -1), _line(get))
                    their_totals = _add(_add(self.totals[partner], _line(get), -1), give_line)
                    pickup = their_drop = None
                    if len(give) == 2:
                        # You have an open spot to fill; they must cut someone
                        if free_agent:
                            my_totals = _add(my_totals, _line(free_agent))
                            pickup = free_agent["name"]
                        left = [p for p in self.players[partner] if p is not get] + give
                        cut = min(left, key=lambda p: self._value(partner, p))
                        their_totals = _add(their_totals, _line(cut), -1)
                        their_value -= self._value(partner, cut)
                        their_drop = cut["name"]
                    if their_value < -FAIR_MARGIN:
                        continue  # they wouldn't say yes
                    changes = {self.me: my_totals, partner: their_totals}
                    gain = self._my_points(changes) - base
                    if gain > 0:
                        found.append((gain, their_value, give, get, pickup, their_drop, changes))

            found.sort(key=lambda t: t[:2], reverse=True)
            # A different player each time, so the list isn't five versions of one deal
            seen = set()
            for gain, their_value, give, get, pickup, their_drop, changes in found:
                shape = len(give)
                if (shape, get["key"]) in seen or sum(s == shape for s, _ in seen) >= TRADES_PER_PARTNER:
                    continue
                seen.add((shape, get["key"]))
                totals = self._with(changes)
                ideas.append({
                    "partner": partner,
                    "partner_name": self._team_name(partner),
                    "give": [p["name"] for p in give],
                    "get": [get["name"]],
                    "pickup": pickup,
                    "their_drop": their_drop,
                    "points_gain": gain,
                    "their_points_change": _points(totals, self.categories)[partner] - base_points[partner],
                    "my_value_change": round(
                        self._value(self.me, get) - sum(self._value(self.me, p) for p in give), 2
                    ),
                    "their_value_change": round(their_value, 2),
                    "category_changes": self._rank_changes(totals),
                })

        def order(t):
            return t["points_gain"], t["their_value_change"]

        ideas.sort(key=order, reverse=True)
        # Leave room for both shapes of deal (1-for-1 and 2-for-1) when both exist
        picked, shapes = [], {}
        for idea in ideas:
            shape = len(idea["give"])
            if shapes.get(shape, 0) < MAX_TRADES - MIN_OTHER_SHAPE:
                picked.append(idea)
                shapes[shape] = shapes.get(shape, 0) + 1
        picked += [i for i in ideas if i not in picked]
        return sorted(picked[:MAX_TRADES], key=order, reverse=True)

    # --- the whole report ---------------------------------------------------

    def advice(self, categories: list[dict]) -> list[dict]:
        """Plain sentences from the numbers: keep, improve, protect, punt."""
        n = len(self.totals)
        tips = []
        counted = [r for r in categories if not r["punted"]]

        strong = [r["category"] for r in counted if r["label"] == "strong"]
        if strong:
            tips.append({"kind": "keep",
                         "text": f"You're strong in {', '.join(strong)}. Keep the players who carry these."})

        close = [r for r in counted if r["gap_up_sd"] is not None and r["gap_up_sd"] <= CLOSE_GAP_SD]
        if close:
            tips.append({
                "kind": "improve",
                "text": "Small gains move you up in "
                + ", ".join(f"{r['category']} (rank {r['rank']}, {r['gap_up']} behind the next team)" for r in close)
                + ". These are the cheapest places to pick up points.",
            })

        thin = [r for r in counted
                if r["label"] != "weak" and r["cushion_sd"] is not None and r["cushion_sd"] <= CLOSE_GAP_SD]
        if thin:
            tips.append({"kind": "protect",
                         "text": f"You could slip in {', '.join(r['category'] for r in thin)}: "
                         "the team behind you is close. Don't trade away what holds these up."})

        far = [r for r in counted if r["label"] == "weak" and (r["gap_up_sd"] or 0) >= FAR_GAP_SD]
        punt = None
        if far and not self.punts:
            worst = max(far, key=lambda r: (r["rank"], r["gap_up_sd"]))
            punt = worst["category"]
            tips.append({
                "kind": "punt",
                "category": punt,
                "text": f"{punt} looks out of reach (rank {worst['rank']} of {n}, far behind). "
                "Consider punting it and trading its value for categories you can win.",
            })

        weak = [r["category"] for r in counted if r["label"] == "weak" and r["category"] != punt]
        if weak:
            tips.append({"kind": "fix",
                         "text": f"Weak spots: {', '.join(weak)}. The trades and pickups below aim at these."})
        return tips

    def report(self) -> dict:
        teams = self.standings()
        categories = self.my_categories()
        me = teams[self.me]
        return {
            "league_name": self.snapshot.name,
            "num_teams": len(self.totals),
            "my_team": {"index": self.me, "name": me["name"], "points": me["points"],
                        "place": me["place"], "players": self._names(self.me)},
            "categories": self.categories,
            "punts": self.punts,
            "teams": teams,
            "my_categories": categories,
            "advice": self.advice(categories),
            "trades": self.trades(),
            "pickups": self.pickups(),
            "drops": self.drops(),
            "unmatched": self.unmatched,
        }
