"""Reading an espn_api basketball League the way the season and draft pages need it:
which categories it scores, which team is mine, who is injured."""

import logging
from typing import Optional

from ...draft.ranker import CATEGORIES

logger = logging.getLogger(__name__)

# ESPN stat ids -> the category keys the ranker knows (espn_api.basketball.constant.STATS_MAP ids)
ESPN_STAT_ID_TO_CATEGORY = {
    0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 6: "REB", 11: "TO",
    17: "3PTM", 19: "FG%", 20: "FT%",
}
OUT_STATUSES = {"OUT", "INJURY_RESERVE", "SUSPENSION", "SUSPENDED", "INJURED_RESERVE"}
QUESTIONABLE_STATUSES = {"DAY_TO_DAY", "QUESTIONABLE", "DOUBTFUL", "PROBABLE"}


def categories(league) -> list[str]:
    """The categories this league scores that we can rank, in ESPN's order. A league
    that isn't category based (points) falls back to the standard nine."""
    raw = getattr(league.settings, "_raw_scoring_settings", None) or {}
    found = []
    for item in raw.get("scoringItems", []) or []:
        category = ESPN_STAT_ID_TO_CATEGORY.get(item.get("statId"))
        if category and category not in found:
            found.append(category)
    return found or list(CATEGORIES)


def unsupported_categories(league) -> list[str]:
    """Scored stat ids we can't rank, as "stat <id>" (ESPN's own names are not in the settings)."""
    raw = getattr(league.settings, "_raw_scoring_settings", None) or {}
    ids = []
    for item in raw.get("scoringItems", []) or []:
        stat = item.get("statId")
        if stat is not None and stat not in ESPN_STAT_ID_TO_CATEGORY and stat not in ids:
            ids.append(stat)
    return [f"stat {i}" for i in ids]


# ESPN lineup slot ids (espn_api.basketball.constant.POSITION_MAP) -> the slot names the app
# uses. The combo slots (SG/SF, G/F, PF/C, F/C) have no match and count as flex; bench (12) and
# injured (13) spots don't start.
ESPN_SLOT_NAMES = {
    0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F",
    7: "Util", 8: "Util", 9: "Util", 10: "Util", 11: "Util",
}


def starting_slots(league) -> dict[str, int]:
    """Starting roster spots, e.g. {"PG": 1, "C": 1, "Util": 3}; {} when ESPN doesn't say.
    espn_api's basketball settings drop the roster settings, so this asks ESPN for them."""
    try:
        data = league.espn_request.league_get(params={"view": "mSettings"})
        counts = data["settings"]["rosterSettings"]["lineupSlotCounts"]
    except Exception as e:
        logger.info(f"ESPN roster slots unavailable: {e}")
        return {}
    slots = {}
    for slot_id, count in (counts or {}).items():
        try:
            mapped, count = ESPN_SLOT_NAMES.get(int(slot_id)), int(count)
        except (TypeError, ValueError):
            continue
        if mapped and count > 0:
            slots[mapped] = slots.get(mapped, 0) + count
    return slots


def my_team(league, swid: Optional[str]):
    """The team owned by this SWID cookie, if it was given."""
    if not swid:
        return None
    for team in league.teams:
        for owner in getattr(team, "owners", None) or []:
            if (owner.get("id") if isinstance(owner, dict) else owner) == swid:
                return team
    return None


def sorted_teams(league) -> list:
    return sorted(league.teams, key=lambda t: t.team_id)


def injury_level(status) -> Optional[str]:
    """ESPN's injuryStatus as "out", "questionable" or None."""
    code = str(status or "").strip().upper()
    if code in OUT_STATUSES:
        return "out"
    if code in QUESTIONABLE_STATUSES:
        return "questionable"
    return None
