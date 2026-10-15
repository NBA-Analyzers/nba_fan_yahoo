"""Injury report and fantasy ownership -> dataset store, so the season tools and the
chat read them instead of calling ESPN on a user request. Cheap: two requests."""

import logging
from datetime import datetime, timezone
from typing import Optional

from ..season import current_season, season_start_year
from ..sinks.datasets import DatasetStore
from ..sources.espn_status import EspnStatusSource

logger = logging.getLogger(__name__)

INJURIES = "injuries"
OWNERSHIP = "ownership"


def run(datasets: DatasetStore, source: Optional[EspnStatusSource] = None) -> dict:
    source = source or EspnStatusSource()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {}

    # One feed failing must not lose the other, so each is stored on its own
    try:
        injuries = source.injuries()
        datasets.put(INJURIES, {"as_of": now, "players": injuries})
        result["injuries"] = len(injuries)
    except Exception as e:
        logger.error("Injury report failed: %s", e)
        result["injuries"] = None

    try:
        ownership = source.ownership(season_start_year(current_season()) + 1)
        if ownership:
            datasets.put(OWNERSHIP, {"as_of": now, "players": ownership})
        result["ownership"] = len(ownership)
    except Exception as e:
        logger.error("Ownership failed: %s", e)
        result["ownership"] = None

    if result["injuries"] is None and result["ownership"] is None:
        raise RuntimeError("Neither the injury report nor ownership could be fetched")
    return result
