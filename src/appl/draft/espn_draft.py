"""Follows an ESPN draft with the same surface the draft page uses for Yahoo and manual
leagues (league_info / state / yahoo_ranks).

espn_api only lists a draft's picks once ESPN marks it finished, so the raw mDraftDetail
response is read instead: it has the picks as they are made.
"""

import logging

from ..fantasy_integrations.espn import espn_league_info as info_helpers
from .yahoo_draft import DEFAULT_AUCTION_BUDGET, DEFAULT_ROSTER_SIZE, next_snake_pick

logger = logging.getLogger(__name__)


class EspnDraftTracker:
    def __init__(self, league, league_id: str, swid: str | None = None, user: str | None = None):
        self.league = league
        self.league_id = league_id
        self._swid = swid
        self.cache_key = f"espn:{league_id}:{user}"
        self._info = None

    # --- raw draft ------------------------------------------------------------

    def _raw(self) -> dict:
        try:
            return self.league.espn_request.get_league_draft() or {}
        except Exception as e:
            logger.error(f"League {self.league_id}: draft fetch failed: {e}")
            raise

    @staticmethod
    def _draft_settings(raw: dict) -> dict:
        return (raw.get("settings") or {}).get("draftSettings") or {}

    @staticmethod
    def _status(raw: dict) -> str:
        detail = raw.get("draftDetail") or {}
        if detail.get("drafted"):
            return "postdraft"
        return "draft" if detail.get("inProgress") else "predraft"

    # --- static league info ---------------------------------------------------

    def league_info(self) -> dict:
        if self._info:
            return self._info
        league = self.league
        teams = info_helpers.sorted_teams(league)
        me = info_helpers.my_team(league, self._swid)
        raw = self._raw()
        draft_settings = self._draft_settings(raw)
        picks = (raw.get("draftDetail") or {}).get("picks") or []
        is_auction = (str(draft_settings.get("type", "")).upper() == "AUCTION"
                      or any((p.get("bidAmount") or 0) > 0 for p in picks))
        order = draft_settings.get("pickOrder") or []
        my_id = getattr(me, "team_id", None)
        budget = draft_settings.get("auctionBudget") or DEFAULT_AUCTION_BUDGET
        roster_size = (max((len(t.roster) for t in teams if getattr(t, "roster", None)), default=0)
                       or DEFAULT_ROSTER_SIZE)
        self._info = {
            "name": getattr(league.settings, "name", None),
            "num_teams": getattr(league.settings, "team_count", None) or len(teams),
            "draft_status": self._status(raw),
            "is_auction": is_auction,
            "stat_categories": [{"display_name": c} for c in info_helpers.categories(league)],
            "roster_size": roster_size,
            "slots": {},
            "my_team_key": my_id,
            "my_draft_position": order.index(my_id) + 1 if my_id in order else None,
            "team_names": {t.team_id: t.team_name for t in teams},
            "budgets": {t.team_id: budget for t in teams},
        }
        return self._info

    # --- live draft -----------------------------------------------------------

    def _name(self, player_id) -> str:
        names = getattr(self.league, "player_map", {}) or {}
        return names.get(player_id) or names.get(str(player_id)) or f"Player {player_id}"

    def state(self, draft_position: int | None = None) -> dict:
        info = self.league_info()
        raw = self._raw()
        results = sorted((raw.get("draftDetail") or {}).get("picks") or [],
                         key=lambda p: p.get("overallPickNumber") or 0)
        picks, spent = [], {tid: 0 for tid in info["team_names"]}
        for index, r in enumerate(results):
            team_id = r.get("teamId")
            cost = int(r.get("bidAmount") or 0) if info["is_auction"] else None
            if cost:
                spent[team_id] = spent.get(team_id, 0) + cost
            picks.append({
                "pick": r.get("overallPickNumber") or index + 1,
                "round": r.get("roundId"),
                "team_key": team_id,
                "team_name": info["team_names"].get(team_id, str(team_id)),
                "player_name": self._name(r.get("playerId")),
                "cost": cost,
                "is_mine": team_id == info["my_team_key"],
            })

        state = {
            "league_name": info["name"],
            "draft_status": self._status(raw),
            "is_auction": info["is_auction"],
            "num_teams": info["num_teams"],
            "roster_size": info["roster_size"],
            "picks": picks,
            "taken_names": [p["player_name"] for p in picks],
            "my_roster": [p["player_name"] for p in picks if p["is_mine"]],
        }
        if info["is_auction"]:
            bought = {tid: 0 for tid in info["budgets"]}
            for p in picks:
                bought[p["team_key"]] = bought.get(p["team_key"], 0) + 1
            teams = []
            for tid, total in info["budgets"].items():
                left = total - spent.get(tid, 0)
                open_spots = max(info["roster_size"] - bought.get(tid, 0), 0)
                teams.append({
                    "team_key": tid, "name": info["team_names"].get(tid, str(tid)),
                    "budget_left": left, "spots_left": open_spots,
                    "max_bid": max(left - open_spots, 0) if open_spots else 0,
                    "is_mine": tid == info["my_team_key"],
                })
            me = next((t for t in teams if t["is_mine"]), None)
            state.update(
                teams=teams,
                my_budget_left=me["budget_left"] if me else 0,
                my_open_spots=me["spots_left"] if me else info["roster_size"],
                league_budget_left=sum(t["budget_left"] for t in teams),
                league_budget_total=sum(info["budgets"].values()),
                league_spots_left=sum(t["spots_left"] for t in teams),
            )
        else:
            position = info["my_draft_position"] or draft_position
            next_pick = next_snake_pick(len(picks), info["num_teams"], position)
            state["needs_draft_position"] = position is None
            state["my_next_pick"] = next_pick
            state["picks_until_my_turn"] = next_pick - len(picks) - 1 if next_pick else None
        return state

    def yahoo_ranks(self) -> dict:
        return {}  # ESPN's own ADP isn't read; the page hides those columns
