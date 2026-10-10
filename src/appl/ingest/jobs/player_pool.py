"""Preseason draft pool and today's in-season pool -> dataset store, so app instances
read them instead of hitting the stats feeds on a user request."""

from datetime import date
from typing import Optional

from ...draft import player_pool


def run(today: Optional[date] = None) -> dict:
    today = today or date.today()
    pool = player_pool.build_player_pool()
    inseason = player_pool.build_inseason_pool(today.isoformat())
    return {
        "season": player_pool.DRAFT_SEASON,
        "preseason_players": len(pool),
        "inseason_players": len(inseason) if inseason is not None else None,
    }
