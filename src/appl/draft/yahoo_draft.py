"""
Follows a live Yahoo draft: who has been picked, by whom, what's left in each
auction budget, and when the manager picks next (snake drafts).
"""

import logging

import yahoo_fantasy_api as yfa

from .player_pool import normalize_name
from .positions import parse_eligible, required_slots

logger = logging.getLogger(__name__)

PLAYER_DETAILS_BATCH = 25
YAHOO_RANK_PAGES = 8  # 8 x 25 = top ~200 players by Yahoo preseason rank
DEFAULT_ROSTER_SIZE = 13
DEFAULT_AUCTION_BUDGET = 200

# league_id -> {yahoo player_id: full name}; names never change mid-draft
_player_names: dict[str, dict[int, str]] = {}
# league_id -> static league info
_league_info: dict[str, dict] = {}
# league_id -> {normalized name: set of Yahoo eligible positions}
_eligibility: dict[str, dict[str, set[str]]] = {}
# league_id -> {normalized name: {"rank", "adp", "avg_cost"}}
_yahoo_ranks: dict[str, dict[str, dict]] = {}


def _to_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def next_snake_pick(picks_made: int, num_teams: int, position: int | None):
    """Overall pick number of the manager's next pick in a snake draft."""
    if not position:
        return None
    rnd = 1
    while True:
        in_round = position if rnd % 2 == 1 else num_teams - position + 1
        overall = (rnd - 1) * num_teams + in_round
        if overall > picks_made:
            return overall
        rnd += 1


def _flatten_player(entry) -> dict:
    """Yahoo returns each player as nested lists of single-key dicts; merge them."""
    merged: dict = {}

    def walk(node):
        if isinstance(node, dict):
            merged.update(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(entry)
    return merged


class YahooDraftTracker:
    def __init__(self, league: yfa.League):
        self.league = league
        self.league_id = league.league_id
        self._names = _player_names.setdefault(self.league_id, {})

    # --- static league info -------------------------------------------------

    def league_info(self) -> dict:
        if self.league_id in _league_info:
            return _league_info[self.league_id]

        settings = self.league.settings()
        teams = self.league.teams()
        my_team_key = next(
            (
                key
                for key, team in teams.items()
                if str(team.get("is_owned_by_current_login")) == "1"
            ),
            None,
        ) or self.league.team_key()

        slots = {}
        try:
            positions = self.league.positions()
            slots = required_slots(positions)
            # Bench counts, injured-list slots don't get drafted into
            roster_size = sum(
                int(p.get("count", 0))
                for name, p in positions.items()
                if name not in ("IL", "IL+")
            )
        except Exception:
            roster_size = DEFAULT_ROSTER_SIZE

        info = {
            "name": settings.get("name"),
            "num_teams": _to_int(settings.get("num_teams"), len(teams) or 12),
            "draft_status": settings.get("draft_status"),
            "is_auction": str(settings.get("is_auction_draft")) == "1",
            "stat_categories": self.league.stat_categories(),
            "roster_size": roster_size or DEFAULT_ROSTER_SIZE,
            "slots": slots,
            "my_team_key": my_team_key,
            "my_draft_position": _to_int(teams.get(my_team_key, {}).get("draft_position")),
            "team_names": {key: t.get("name") for key, t in teams.items()},
            "budgets": {
                key: _to_int(t.get("auction_budget_total"), DEFAULT_AUCTION_BUDGET)
                for key, t in teams.items()
            },
        }
        _league_info[self.league_id] = info
        return info

    # --- live draft ---------------------------------------------------------

    def _resolve_names(self, player_ids: list[int]):
        missing = [pid for pid in set(player_ids) if pid not in self._names]
        for i in range(0, len(missing), PLAYER_DETAILS_BATCH):
            batch = missing[i : i + PLAYER_DETAILS_BATCH]
            try:
                for details in self.league.player_details(batch):
                    self._names[int(details["player_id"])] = details["name"]["full"]
            except Exception as e:
                logger.error(f"League {self.league_id}: player lookup failed: {e}")

    def state(self, draft_position: int | None = None) -> dict:
        """`draft_position` is the manager's own slot, used when Yahoo doesn't expose it."""
        info = self.league_info()
        results = sorted(self.league.draft_results(), key=lambda r: _to_int(r["pick"], 0))
        self._resolve_names([int(r["player_id"]) for r in results])

        picks = []
        spent = {key: 0 for key in info["team_names"]}
        for r in results:
            pid = int(r["player_id"])
            cost = _to_int(r.get("cost"), 0) if info["is_auction"] else None
            if cost:
                spent[r["team_key"]] = spent.get(r["team_key"], 0) + cost
            picks.append(
                {
                    "pick": _to_int(r["pick"]),
                    "round": _to_int(r.get("round")),
                    "team_key": r["team_key"],
                    "team_name": info["team_names"].get(r["team_key"], r["team_key"]),
                    "player_name": self._names.get(pid, f"Player {pid}"),
                    "cost": cost,
                    "is_mine": r["team_key"] == info["my_team_key"],
                }
            )

        state = {
            "league_name": info["name"],
            "draft_status": info["draft_status"],
            "is_auction": info["is_auction"],
            "num_teams": info["num_teams"],
            "roster_size": info["roster_size"],
            "picks": picks,
            "taken_names": [p["player_name"] for p in picks],
            "my_roster": [p["player_name"] for p in picks if p["is_mine"]],
        }

        if info["is_auction"]:
            budgets = info["budgets"]
            bought = {key: 0 for key in budgets}
            for pick in picks:
                bought[pick["team_key"]] = bought.get(pick["team_key"], 0) + 1
            teams = []
            for key, total in budgets.items():
                left = total - spent.get(key, 0)
                open_spots = max(info["roster_size"] - bought.get(key, 0), 0)
                teams.append(
                    {
                        "team_key": key,
                        "name": info["team_names"].get(key, key),
                        "budget_left": left,
                        "spots_left": open_spots,
                        # Most they can bid and still keep $1 for every open spot
                        "max_bid": max(left - open_spots, 0) if open_spots else 0,
                        "is_mine": key == info["my_team_key"],
                    }
                )
            me = next((t for t in teams if t["is_mine"]), None)
            state["teams"] = teams
            state["my_budget_left"] = me["budget_left"] if me else 0
            state["my_open_spots"] = me["spots_left"] if me else info["roster_size"]
            state["league_budget_left"] = sum(t["budget_left"] for t in teams)
            state["league_budget_total"] = sum(budgets.values())
            state["league_spots_left"] = sum(t["spots_left"] for t in teams)
        else:
            position = info["my_draft_position"] or draft_position
            next_pick = next_snake_pick(len(picks), info["num_teams"], position)
            state["needs_draft_position"] = position is None
            state["my_next_pick"] = next_pick
            state["picks_until_my_turn"] = (
                next_pick - len(picks) - 1 if next_pick else None
            )
        return state

    # --- positions ----------------------------------------------------------

    def eligible_positions(self, name: str) -> set[str] | None:
        """Yahoo's eligible positions for a player (looked up once, then cached).
        None if Yahoo can't find the player, so callers can skip the position check."""
        cache = _eligibility.setdefault(self.league_id, {})
        key = normalize_name(name)
        if key in cache:
            return cache[key] or None
        found: set[str] = set()
        try:
            matches = self.league.player_details(name)
            exact = [
                m for m in matches
                if normalize_name(m.get("name", {}).get("full", "")) == key
            ]
            chosen = (exact or matches or [None])[0]
            if chosen:
                found = parse_eligible(chosen.get("eligible_positions"))
        except Exception as e:
            logger.warning(f"League {self.league_id}: position lookup for {name} failed: {e}")
            return None  # not cached, so a later poll can retry
        cache[key] = found
        return found or None

    # --- Yahoo preseason rank / ADP ----------------------------------------

    def yahoo_ranks(self) -> dict[str, dict]:
        """Normalized name -> {"rank": preseason rank, "adp": average pick}.

        Best effort: Yahoo's response shape is parsed defensively and an empty
        dict is returned on any failure, so the page just hides those columns.
        """
        if self.league_id in _yahoo_ranks:
            return _yahoo_ranks[self.league_id]

        ranks: dict[str, dict] = {}
        try:
            for page in range(YAHOO_RANK_PAGES):
                start = page * 25
                uri = (
                    f"league/{self.league.league_id}/players;"
                    f"sort=OR;start={start};count=25/draft_analysis"
                )
                raw = self.league.yhandler.get(uri)
                players = _extract_players(raw)
                if not players:
                    break
                for offset, player in enumerate(players):
                    name = player.get("name", {}).get("full")
                    if not name:
                        continue
                    analysis = _flatten_player(player.get("draft_analysis", []))
                    ranks[normalize_name(name)] = {
                        "rank": start + offset + 1,
                        "adp": _to_float(analysis.get("average_pick")),
                        # Auction leagues: what the player has averaged in Yahoo auctions
                        "avg_cost": _to_float(analysis.get("average_cost")),
                    }
        except Exception as e:
            logger.warning(f"League {self.league_id}: Yahoo rank lookup failed: {e}")
            return {}

        _yahoo_ranks[self.league_id] = ranks
        return ranks


def _extract_players(raw: dict) -> list[dict]:
    """Pull the player dicts out of a league/players response."""
    try:
        container = raw["fantasy_content"]["league"][1]["players"]
    except (KeyError, IndexError, TypeError):
        return []
    players = []
    for key, value in container.items():
        if key == "count" or not isinstance(value, dict):
            continue
        players.append(_flatten_player(value.get("player", [])))
    return players
