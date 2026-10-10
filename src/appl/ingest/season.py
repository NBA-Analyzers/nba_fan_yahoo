"""NBA season labels ("2026-27"), worked out from the date instead of hard-coded.

From July on, the coming season is "current": draft prep in the offseason targets it,
and in-season stats for it simply come back empty until tip-off.
"""

from datetime import date
from typing import Optional

ROLLOVER_MONTH = 7


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_start_year(season: str) -> int:
    try:
        return int(season.split("-")[0])
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid season {season!r}; expected 'YYYY-YY'")


def current_season(today: Optional[date] = None) -> str:
    today = today or date.today()
    year = today.year if today.month >= ROLLOVER_MONTH else today.year - 1
    return season_label(year)


def previous_season(season: str, back: int = 1) -> str:
    return season_label(season_start_year(season) - back)


def season_end(season: str) -> date:
    """A safe upper bound for the last regular-season game (it ends mid-April)."""
    return date(season_start_year(season) + 1, 4, 30)


def yahoo_game_year(season: str) -> int:
    """Yahoo names an NBA season by its start year: 2026-27 -> 2026."""
    return season_start_year(season)
