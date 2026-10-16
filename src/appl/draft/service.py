"""The draft assistant's logic: turns a tracker (Yahoo, ESPN or a hand-run league) and the
request options into the state, recommendations and advice the draft page shows. The routes
only parse the request and map errors; nothing here knows about Flask."""

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from . import advice, jev_chooser, positions
from .player_pool import load_player_pool
from .ranker import DraftRanker, categories_from_yahoo
from .yahoo_draft import DEFAULT_AUCTION_BUDGET

logger = logging.getLogger(__name__)

MAX_RANKERS = 64  # a ranker holds the whole player pool, so keep only the recently used ones


@dataclass
class StateOptions:
    """What the manager asked for on this refresh."""

    punts: list = field(default_factory=list)
    mock: bool = False
    auto_punts: bool = False
    mode: str = "manual"
    preference: str = ""
    nominee: str = ""
    draft_position: int | None = None
    mock_taken: list = field(default_factory=list)
    mock_mine: list = field(default_factory=list)
    mock_costs: dict | None = None


def mock_auction_state(info: dict, taken: list, mine: list, costs) -> dict:
    """Budgets for a hand-run mock auction: everyone starts with the default budget
    and only the prices the manager typed in are spent."""
    costs = {k: int(v) for k, v in (costs or {}).items() if str(v).lstrip("-").isdigit()}
    total = info["num_teams"] * DEFAULT_AUCTION_BUDGET
    return {
        "league_budget_total": total,
        "league_budget_left": total - sum(costs.get(n, 0) for n in taken),
        "my_budget_left": DEFAULT_AUCTION_BUDGET - sum(costs.get(n, 0) for n in mine),
        "my_open_spots": max(info["roster_size"] - len(mine), 0),
        "league_spots_left": max(info["num_teams"] * info["roster_size"] - len(taken), 0),
        "teams": [],
    }


def eligibility_lookup(tracker, ranker):
    """Spots a player can fill: Yahoo's answer for Yahoo leagues, otherwise (and when
    Yahoo can't find the player) the position listed in the stats pool."""

    def lookup(name):
        found = tracker.eligible_positions(name) if hasattr(tracker, "eligible_positions") else None
        if found:
            return found
        player = ranker.find(name)
        return positions.eligible_from_listed_position(player.get("pos")) if player else None

    return lookup


def position_report(lookup, info: dict, mine: list) -> dict | None:
    """Which starting slots the roster can't fill yet (warn-only). None if the
    league's slots aren't known."""
    slots = info.get("slots")
    if not slots:
        return None
    eligible = [lookup(name) for name in mine]
    report = positions.roster_report([e or {positions.FLEX_SLOT} for e in eligible], slots)
    report["incomplete"] = any(e is None for e in eligible)
    return report


THIN_PACE = 0.6  # warn when winning would leave under this share of the room's average $ per open spot


def bid_pace(state: dict, bid: int) -> dict:
    """What winning at `bid` does to your money for the remaining spots."""
    left, spots = state.get("my_budget_left"), state.get("my_open_spots")
    room_left, room_spots = state.get("league_budget_left"), state.get("league_spots_left")
    if None in (left, spots, room_left, room_spots) or spots <= 0 or not room_spots:
        return {}
    spots_after = spots - 1
    left_after = left - bid
    room_avg = room_left / room_spots
    per_spot = left_after / spots_after if spots_after else None
    pace = {
        "walk_away_above": bid,
        "left_after_bid": left_after,
        "spots_after_bid": spots_after,
        "per_spot_after_bid": round(per_spot, 1) if per_spot is not None else None,
        "room_avg_per_spot": round(room_avg, 1),
        "thin_after_bid": bool(spots_after and per_spot < THIN_PACE * room_avg),
    }
    return pace


def nominee_card(nominee, lookup, ranker, info, state, plan, punts, taken, mine) -> dict | None:
    """Everything the manager needs while a player is on the block."""
    if not nominee or not state["is_auction"]:
        return None
    player = ranker.find(nominee)
    if player is None:
        return {"query": nominee, "found": False}

    name = player["name"]
    card = {"query": nominee, "found": True, "name": name, "team": player["team"]}

    sale = next((p for p in state.get("picks", []) if ranker.resolve_key(p["player_name"]) == player["key"]), None)
    if sale or ranker.resolve_key(name) in {ranker.resolve_key(t) for t in taken}:
        card.update(sold=True, sold_to=sale["team_name"] if sale else None,
                    cost=sale["cost"] if sale else None)
        return card

    ranked = ranker.rank(punts=punts, taken_names=taken, my_roster_names=mine, limit=len(ranker.players))
    rec = next((r for r in ranked if r["name"] == name), None)
    my_value, market = plan["mine"].get(name, 1), plan["market"].get(name, 1)
    max_bid = plan["max_bid"]
    avg_cost = ranker.yahoo_ranks.get(player["key"], {}).get("avg_cost")

    if my_value >= market:
        verdict = "target"      # worth at least what the room will pay
    elif my_value >= 0.8 * market:
        verdict = "fair"
    else:
        verdict = "overpriced"  # the room will likely pay more than he's worth to you

    card.update(bid_pace(state, min(my_value, max_bid)))

    teams = [t for t in state.get("teams", []) if not t["is_mine"]]
    card.update(
        sold=False,
        my_value=my_value,
        market=market,
        yahoo_avg_cost=avg_cost,
        max_bid=max_bid,
        bid_up_to=min(my_value, max_bid),
        verdict=verdict,
        my_rank=ranked.index(rec) + 1 if rec else None,
        z=rec["z"] if rec else player["z"],
        strengths=rec["strengths"] if rec else [],
        weaknesses=rec["weaknesses"] if rec else [],
        rivals_who_can_pay_market=sum(t["max_bid"] >= market for t in teams) if teams else None,
        richest_rivals=[
            {"name": t["name"], "max_bid": t["max_bid"]}
            for t in sorted(teams, key=lambda t: t["max_bid"], reverse=True)[:3]
        ],
    )

    slots = info.get("slots")
    if slots:
        roster = [lookup(n) or {positions.FLEX_SLOT} for n in mine]
        nominee_slots = lookup(name)
        if nominee_slots:
            report = positions.roster_report(roster, slots, nominee_slots)
            card["fills_open_slot"] = report["fills_open_slot"]
            card["eligible"] = sorted(nominee_slots - {positions.FLEX_SLOT})
    return card


class DraftService:
    def __init__(self, max_rankers: int = MAX_RANKERS):
        self._max_rankers = max_rankers
        self._rankers: OrderedDict[str, DraftRanker] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def cached_rankers(self) -> int:
        return len(self._rankers)

    def _cached(self, key: str, build) -> DraftRanker:
        """The ranker stored under `key`, built on first use; evicts the least recently
        used one past the limit."""
        with self._lock:
            if key in self._rankers:
                self._rankers.move_to_end(key)
                return self._rankers[key]
        ranker = build()
        with self._lock:
            self._rankers[key] = ranker
            self._rankers.move_to_end(key)
            while len(self._rankers) > self._max_rankers:
                self._rankers.popitem(last=False)
        return ranker

    def ranker_for(self, league_id: str, tracker) -> DraftRanker:
        """The ranker for this league, kept per tracker `cache_key` so a setting change
        or another user gets its own."""

        def build():
            info = tracker.league_info()
            return DraftRanker(
                load_player_pool(),
                categories=categories_from_yahoo(info["stat_categories"]),
                num_teams=info["num_teams"],
                roster_size=info["roster_size"],
                yahoo_ranks=tracker.yahoo_ranks(),
            )

        return self._cached(getattr(tracker, "cache_key", league_id), build)

    def names_ranker(self) -> DraftRanker:
        """Default settings; only used to match typed names to the player pool."""
        return self._cached("names", lambda: DraftRanker(load_player_pool()))

    def state(self, league_id: str, tracker, options: StateOptions) -> dict:
        """Draft state + recommendations for whichever tracker the caller built."""
        punts, mode, preference = options.punts, options.mode, options.preference
        nominee, auto_punts = options.nominee, options.auto_punts
        mock_taken, mock_mine, mock_costs = options.mock_taken, options.mock_mine, options.mock_costs
        mock, draft_position = options.mock, options.draft_position

        ranker = self.ranker_for(league_id, tracker)
        info = tracker.league_info()
        lookup = eligibility_lookup(tracker, ranker)

        if mock:
            taken, mine = mock_taken, mock_mine
            state = {
                "league_name": info["name"],
                "is_auction": info["is_auction"],
                "num_teams": info["num_teams"],
                "roster_size": info["roster_size"],
                "picks": [],
                "taken_names": taken,
                "my_roster": mine,
                "mock": True,
            }
            if info["is_auction"]:
                state.update(mock_auction_state(info, taken, mine, mock_costs))
        else:
            state = tracker.state(draft_position)
            taken, mine = state["taken_names"], state["my_roster"]

        # Once a few players are on the team: which one category to skip, and what that
        # does to the best available. With auto_punts it is applied to everything below.
        suggestion = advice.build_suggestion(ranker, mine, punts, taken)
        chosen_punts = punts
        if auto_punts and suggestion:
            chosen_punts = punts + [suggestion["category"]]
        user_punts, punts = punts, chosen_punts

        recommendations = ranker.rank(
            punts=punts, taken_names=taken, my_roster_names=mine
        )

        plan = None
        if state["is_auction"]:
            plan = ranker.auction_plan(
                punts, taken, mine,
                league_budget_left=state["league_budget_left"],
                league_budget_total=state["league_budget_total"],
                league_spots_left=state["league_spots_left"],
                my_budget_left=state["my_budget_left"],
                my_open_spots=state["my_open_spots"],
            )
            for rec in recommendations:
                rec["bid"] = plan["mine"].get(rec["name"])
                rec["market"] = plan["market"].get(rec["name"])
            state["auction"] = {
                "inflation_pct": plan["inflation_pct"],
                "max_bid": plan["max_bid"],
            }
            state["cash_advice"] = advice.cash_advice(plan, state)

        roster_profile = ranker.roster_profile(mine)
        decision = jev_chooser.decide(
            mode,
            recommendations[: jev_chooser.SHORTLIST_SIZE],
            mine,
            punts,
            ranker.categories,
            roster_profile,
            preference,
        )

        return {
            **state,
            "decision": decision,
            "jev_configured": jev_chooser.is_configured(),
            "categories": ranker.categories,
            "punts": user_punts,
            "effective_punts": punts,
            "auto_punts": auto_punts,
            "build_suggestion": suggestion,
            "suggested_punts": ranker.suggest_punts(mine),
            "roster_profile": roster_profile,
            "roster_unmatched": ranker.unmatched(mine),
            "taken_unmatched": ranker.unmatched(taken),
            "has_yahoo_ranks": bool(ranker.yahoo_ranks),
            "recommendations": recommendations,
            "positions": position_report(lookup, info, mine),
            "nominee_card": nominee_card(
                nominee, lookup, ranker, info, state, plan, punts, taken, mine
            ),
        }
