"""
Category-based (z-score) draft rankings with punt support.

Pure functions / no I/O. Percentage categories are volume-weighted (a 60%
shooter on 2 attempts matters less than on 15). Punted categories are
dropped from the score, and once the manager has a few players, categories
the roster is weak in get a boost.
"""

from difflib import get_close_matches
from statistics import mean, pstdev

from .player_pool import normalize_name

CATEGORIES = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"]

# Yahoo stat_categories() display names -> internal keys
YAHOO_CATEGORY_ALIASES = {
    "FG%": "FG%", "FT%": "FT%", "3PTM": "3PTM", "PTS": "PTS", "REB": "REB",
    "AST": "AST", "ST": "STL", "STL": "STL", "BLK": "BLK", "TO": "TO",
}

COUNTING_STATS = {
    "3PTM": "FG3M", "PTS": "PTS", "REB": "REB", "AST": "AST",
    "STL": "STL", "BLK": "BLK", "TO": "TOV",
}
PERCENT_STATS = {"FG%": ("FGM", "FGA"), "FT%": ("FTM", "FTA")}
NEGATIVE_CATEGORIES = {"TO"}

MIN_GAMES = 15
FULL_SEASON_GAMES = 70
NEED_MIN_ROSTER = 3
NEED_SWING = 0.5  # need weights range 1 +/- this (tuned in mock drafts: 0.5 beat 0.25, 1.0 and 1.5)
FUZZY_NAME_CUTOFF = 0.88  # similarity needed to treat two spellings as one player
VALUE_RANK_GAP = 15  # our rank this far ahead of Yahoo ADP => "value"


def categories_from_yahoo(stat_categories: list[dict]) -> list[str]:
    """Map a league's Yahoo stat categories to the ones we can rank."""
    mapped = [
        YAHOO_CATEGORY_ALIASES[c["display_name"]]
        for c in stat_categories
        if c.get("display_name") in YAHOO_CATEGORY_ALIASES
    ]
    return mapped or CATEGORIES


def _league_pcts(players: list[dict]) -> dict:
    pcts = {}
    for category, (made, attempts) in PERCENT_STATS.items():
        total = sum(p[attempts] for p in players)
        pcts[category] = sum(p[made] for p in players) / total if total else 0.0
    return pcts


def _values(players: list[dict], category: str, league_pcts: dict) -> list[float]:
    if category in COUNTING_STATS:
        return [p[COUNTING_STATS[category]] for p in players]
    made, attempts = PERCENT_STATS[category]
    # Makes above what a league-average shooter would get on the same volume
    return [p[made] - league_pcts[category] * p[attempts] for p in players]


def _zscores(players: list[dict], baseline: list[dict], categories: list[str]):
    league_pcts = _league_pcts(baseline)
    result = [{} for _ in players]
    for category in categories:
        base = _values(baseline, category, league_pcts)
        mu, sigma = mean(base), pstdev(base) or 1.0
        for i, value in enumerate(_values(players, category, league_pcts)):
            z = (value - mu) / sigma
            result[i][category] = -z if category in NEGATIVE_CATEGORIES else z
    return result


class DraftRanker:
    def __init__(
        self,
        player_pool: list[dict],
        categories: list[str] | None = None,
        num_teams: int = 12,
        roster_size: int = 13,
        yahoo_ranks: dict[str, dict] | None = None,
    ):
        """yahoo_ranks: normalized name -> {"rank": int, "adp": float}"""
        self.categories = categories or CATEGORIES
        self.num_teams = num_teams
        self.roster_size = roster_size
        self.yahoo_ranks = yahoo_ranks or {}

        eligible = [p for p in player_pool if p["GP"] >= MIN_GAMES]
        first_pass = _zscores(eligible, eligible, self.categories)
        ranked = sorted(
            zip(eligible, first_pass), key=lambda pz: sum(pz[1].values()), reverse=True
        )
        # Z-scores are measured against the players who will actually be drafted
        draftable = [p for p, _ in ranked[: num_teams * roster_size]] or eligible
        zscores = _zscores(eligible, draftable, self.categories)

        self.players = [
            {
                **player,
                "key": normalize_name(player["name"]),
                "z": {c: round(v, 2) for c, v in z.items()},
            }
            for player, z in zip(eligible, zscores)
        ]
        self._by_key = {p["key"]: p for p in self.players}
        self._fuzzy_cache: dict[str, str | None] = {}

        # Overall rank with no punts and no roster context, to compare against Yahoo
        self._base_rank = {
            p["key"]: i + 1
            for i, p in enumerate(
                sorted(self.players, key=lambda p: sum(p["z"].values()), reverse=True)
            )
        }

    def resolve_key(self, name: str) -> str | None:
        """Pool key for a Yahoo/NBA spelling: exact after normalizing, else a
        close match (e.g. 'Nicolas Claxton' vs 'Nic Claxton'). None if unknown."""
        key = normalize_name(name)
        if key in self._by_key:
            return key
        if key in self._fuzzy_cache:
            return self._fuzzy_cache[key]
        close = get_close_matches(key, self._by_key, n=1, cutoff=FUZZY_NAME_CUTOFF)
        self._fuzzy_cache[key] = close[0] if close else None
        return self._fuzzy_cache[key]

    def find(self, name: str) -> dict | None:
        key = self.resolve_key(name)
        return self._by_key[key] if key else None

    def suggest_names(self, name: str, limit: int = 4) -> list[str]:
        """Pool names a typed name probably meant: every word typed appears in the
        name (so 'jokic' finds Nikola Jokic), then looser spelling matches."""
        query = normalize_name(name)
        if not query:
            return []
        words = query.split()
        keys = [k for k in self._by_key if all(any(t.startswith(w) for t in k.split()) for w in words)]
        keys += [k for k in get_close_matches(query, self._by_key, n=limit, cutoff=0.6) if k not in keys]
        return [self._by_key[k]["name"] for k in keys[:limit]]

    def unmatched(self, names: list[str]) -> list[str]:
        """Names with no stats in the pool (they can't be excluded or scored)."""
        return [n for n in names if self.resolve_key(n) is None]

    def _taken_keys(self, names: list[str] | None) -> set[str]:
        return {self.resolve_key(n) or normalize_name(n) for n in (names or [])}

    def roster_profile(self, roster_names: list[str]) -> dict:
        """Average z-score per category over the roster's players."""
        roster = [p for p in map(self.find, roster_names) if p]
        if not roster:
            return {c: 0.0 for c in self.categories}
        return {c: round(mean(p["z"][c] for p in roster), 2) for c in self.categories}

    def suggest_punts(self, roster_names: list[str], count: int = 2) -> list[str]:
        """The roster's weakest categories - natural punt candidates."""
        if len([n for n in roster_names if self.find(n)]) < NEED_MIN_ROSTER:
            return []
        profile = self.roster_profile(roster_names)
        return sorted(profile, key=profile.get)[:count]

    def _need_weights(self, roster_names: list[str], punts: set[str]) -> dict:
        weights = {c: 1.0 for c in self.categories if c not in punts}
        if len([n for n in roster_names if self.find(n)]) < NEED_MIN_ROSTER:
            return weights
        profile = self.roster_profile(roster_names)
        for category in weights:
            # Weak category (negative avg z) -> up to +25%, strong -> down to -25%
            weights[category] = 1.0 + max(-1.0, min(1.0, -profile[category])) * NEED_SWING
        return weights

    @staticmethod
    def _availability(player: dict) -> float:
        return 0.85 + 0.15 * min(player["GP"] / FULL_SEASON_GAMES, 1.0)

    def _fit(self, player: dict, weights: dict) -> float:
        """A player's worth to this build: weighted z over counted categories."""
        return sum(player["z"][c] * w for c, w in weights.items()) * self._availability(player)

    def rank(
        self,
        punts: list[str] | None = None,
        taken_names: list[str] | None = None,
        my_roster_names: list[str] | None = None,
        limit: int = 25,
    ) -> list[dict]:
        punts = {p for p in (punts or []) if p in self.categories}
        taken = self._taken_keys(taken_names)
        weights = self._need_weights(my_roster_names or [], punts)

        recs = []
        for player in self.players:
            if player["key"] in taken:
                continue
            punt_value = sum(player["z"][c] for c in weights)
            yahoo = self.yahoo_ranks.get(player["key"], {})
            adp = yahoo.get("adp")
            recs.append(
                {
                    "name": player["name"],
                    "team": player["team"],
                    "games_played": int(player["GP"]),
                    "minutes": round(player["MIN"], 1),
                    "score": round(self._fit(player, weights), 2),
                    "punt_value": round(punt_value, 2),
                    "z": player["z"],
                    "strengths": [c for c in weights if player["z"][c] >= 1.0],
                    "weaknesses": [c for c in weights if player["z"][c] <= -1.0],
                    "yahoo_rank": yahoo.get("rank"),
                    "adp": adp,
                    "_base_rank": self._base_rank[player["key"]],
                }
            )

        recs.sort(key=lambda r: r["score"], reverse=True)
        for position, rec in enumerate(recs, start=1):
            adp = rec["adp"]
            # Our (punt-adjusted) rank is well ahead of where Yahoo drafters take him
            rec["value"] = bool(adp and adp - position >= VALUE_RANK_GAP)
            rec.pop("_base_rank")
        return recs[:limit]

    def auction_values(
        self, budget: int, spots: int | None = None, taken_names: list[str] | None = None
    ) -> dict[str, int]:
        """Generic price per remaining player who still makes a roster, scaled to
        the money left in the league."""
        taken = self._taken_keys(taken_names)
        spots = spots or self.num_teams * self.roster_size
        measures = {
            p["name"]: sum(p["z"].values()) for p in self.players if p["key"] not in taken
        }
        prices = _price_table(measures, budget, spots)
        drafted = sorted(measures, key=measures.get, reverse=True)[:spots]
        return {name: prices[name] for name in drafted}

    def auction_plan(
        self,
        punts: list[str],
        taken_names: list[str],
        my_roster_names: list[str],
        league_budget_left: int,
        league_budget_total: int,
        league_spots_left: int,
        my_budget_left: int,
        my_open_spots: int,
    ) -> dict:
        """Auction numbers that follow the draft as it happens.

        market  - what the room will probably pay (generic value, so it already
                  reflects inflation: the money left divided over the players left)
        mine    - what a player is worth to YOUR build (punts + roster needs), priced
                  on the same dollar scale so the two are comparable
        max_bid - the most you can bid and still keep $1 for every open roster spot
                  (Yahoo's rule; shown conservatively)
        """
        taken = self._taken_keys(taken_names)
        punt_set = {p for p in punts if p in self.categories}
        weights = self._need_weights(my_roster_names, punt_set)
        remaining = [p for p in self.players if p["key"] not in taken]
        spots = max(league_spots_left, 1)

        generic = {p["name"]: sum(p["z"].values()) for p in remaining}
        market = _price_table(generic, league_budget_left, spots)
        mine = _price_table(
            {p["name"]: self._fit(p, weights) for p in remaining}, league_budget_left, spots
        )

        # Inflation: today's price of the players still in play vs their pre-draft price
        everyone = {p["name"]: sum(p["z"].values()) for p in self.players}
        base = _price_table(everyone, league_budget_total, self.num_teams * self.roster_size)
        in_play = sorted(generic, key=generic.get, reverse=True)[:spots]
        base_sum = sum(base[n] for n in in_play)
        inflation = sum(market[n] for n in in_play) / base_sum - 1 if base_sum else 0.0

        return {
            "market": market,
            "mine": mine,
            "inflation_pct": round(inflation * 100, 1),
            "max_bid": max(my_budget_left - my_open_spots, 0) if my_open_spots > 0 else 0,
        }


def _price_table(measures: dict[str, float], money: float, spots: int) -> dict[str, int]:
    """Dollar price per player: $1 each, with the rest of `money` split by value
    above the last player who still makes a roster. Everyone else costs $1."""
    ranked = sorted(measures.items(), key=lambda kv: kv[1], reverse=True)[:spots]
    prices = {name: 1 for name in measures}
    if not ranked:
        return prices
    replacement = ranked[-1][1]
    total_surplus = sum(v - replacement for _, v in ranked) or 1.0
    spendable = max(money - spots, 0)
    for name, value in ranked:
        prices[name] = max(1, round(1 + spendable * (value - replacement) / total_surplus))
    return prices
