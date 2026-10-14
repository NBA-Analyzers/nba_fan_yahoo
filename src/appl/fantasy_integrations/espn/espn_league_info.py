"""Reading an espn_api basketball League the way the season and draft pages need it:
which categories it scores, which team is mine, who is injured."""

from typing import Optional

from ...draft.ranker import CATEGORIES

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
