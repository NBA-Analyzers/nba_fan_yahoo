"""Typed shapes for ingested data. Sources validate rows here before anything is stored,
so a changed upstream payload shows up as a rejected-row count, not a KeyError later."""

import logging
from typing import Iterable, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SeasonLine(_Row):
    """A player's per-game averages for one season (ESPN or nba_api)."""

    nba_id: int
    name: str = Field(min_length=1)
    team: Optional[str] = None
    pos: Optional[str] = None
    GP: float = Field(ge=0)
    MIN: float = 0.0
    PTS: float = 0.0
    REB: float = 0.0
    AST: float = 0.0
    STL: float = 0.0
    BLK: float = 0.0
    TOV: float = 0.0
    FG3M: float = 0.0
    FGM: float = 0.0
    FGA: float = 0.0
    FTM: float = 0.0
    FTA: float = 0.0


class ScheduledGame(_Row):
    game_id: str
    date: str  # YYYY-MM-DD
    home_team: str
    away_team: str


class Matchup(_Row):
    week: int
    teams: list[str]
    winner: Optional[str] = None  # team name; None for a tie or an unfinished week
    stats: dict[str, dict[str, str]] = {}


class TooManyRejected(RuntimeError):
    pass


def validate_rows(model: Type[M], rows: Iterable[dict], *, source: str,
                  max_reject_ratio: float = 0.2) -> list[M]:
    """Valid rows as models. Bad rows are logged and dropped; if more than
    `max_reject_ratio` are bad the upstream format has probably changed, so fail loudly."""
    valid, rejected, total = [], 0, 0
    for row in rows:
        total += 1
        try:
            valid.append(model.model_validate(row))
        except ValidationError as e:
            rejected += 1
            if rejected <= 5:
                logger.warning("%s: rejected row (%s)", source, e.errors()[0].get("msg"))
    if rejected:
        logger.warning("%s: %d/%d rows rejected", source, rejected, total)
    if total and rejected / total > max_reject_ratio:
        raise TooManyRejected(f"{source}: {rejected}/{total} rows failed validation")
    return valid
