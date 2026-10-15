"""What the nightly jobs know about players beyond the season line: the injury report,
fantasy ownership and recent-form windows (last 7 / 14 / 30 days). Read from the
dataset store and cached briefly; every lookup works with nothing loaded."""

import logging
import threading
import time
from datetime import date

from ..draft.player_pool import normalize_name
from ..ingest.season import current_season

logger = logging.getLogger(__name__)

CACHE_SECONDS = 15 * 60
MIN_RECENT_GAMES = 3  # a minutes trend over fewer games than this is noise

# The stats report's friendly column names -> short keys for the model
_WINDOW_KEYS = {
    "Games Played": "games", "Average Minutes": "min", "Points": "pts", "Rebounds": "reb",
    "Assists": "ast", "Steals": "stl", "Blocks": "blk", "Turnovers": "tov", "3PT Made": "3pm",
    "Field Goal Percentage": "fg_pct", "Free Throw Percentage": "ft_pct",
}
WINDOWS = ("last_7_days", "last_14_days", "last_30_days")


def _by_key(rows: dict) -> dict:
    return {normalize_name(name): row for name, row in (rows or {}).items()}


class PlayerData:
    def __init__(self, injuries: dict | None = None, ownership: dict | None = None,
                 stats: dict | None = None, injuries_as_of: str | None = None,
                 ownership_as_of: str | None = None):
        self._injuries = _by_key(injuries)
        self._ownership = _by_key(ownership)
        self._stats = _by_key(stats)
        self.injuries_as_of = injuries_as_of
        self.ownership_as_of = ownership_as_of

    @classmethod
    def empty(cls) -> "PlayerData":
        return cls()

    # --- injuries -----------------------------------------------------------

    def injury_levels(self) -> dict[str, str]:
        """name -> "out" | "questionable", ready to merge into a league snapshot."""
        return {key: row["level"] for key, row in self._injuries.items() if row.get("level")}

    def injury(self, name: str) -> dict | None:
        row = self._injuries.get(normalize_name(name))
        if not row:
            return None
        return {"level": row.get("level"), "status": row.get("status"), "note": row.get("note"),
                "reported": row.get("date")}

    # --- ownership ----------------------------------------------------------

    def ownership(self, name: str) -> dict | None:
        return self._ownership.get(normalize_name(name))

    # --- recent form --------------------------------------------------------

    def form(self, name: str) -> dict | None:
        """Recent windows in short keys, plus the minutes trend (last 14 days vs the season)."""
        row = self._stats.get(normalize_name(name))
        if not row:
            return None
        out = {}
        for window in WINDOWS:
            stats = row.get(window)
            if stats:
                out[window] = {short: stats[friendly] for friendly, short in _WINDOW_KEYS.items()
                               if stats.get(friendly) is not None}
        season = row.get("season") or {}
        out["season_min"] = season.get("Minutes")
        out["minutes_trend"] = self._minutes_trend(out)
        return out if any(w in out for w in WINDOWS) else None

    @staticmethod
    def _minutes_trend(form: dict) -> float | None:
        recent, season = form.get("last_14_days"), form.get("season_min")
        if not recent or season is None or (recent.get("games") or 0) < MIN_RECENT_GAMES:
            return None
        if recent.get("min") is None:
            return None
        return round(recent["min"] - season, 1)

    def risers(self, names: list[str], limit: int = 8) -> list[dict]:
        """Of `names`, those playing the most extra minutes lately (a role change shows
        in minutes before it shows in stats)."""
        rows = []
        for name in names:
            form = self.form(name)
            if form and form.get("minutes_trend") is not None:
                rows.append({"name": name, "minutes_trend": form["minutes_trend"],
                             "last_14_days": form.get("last_14_days"), "season_min": form["season_min"]})
        rows.sort(key=lambda r: r["minutes_trend"], reverse=True)
        return [r for r in rows if r["minutes_trend"] > 0][:limit]


_cache: tuple[float, PlayerData] | None = None
_lock = threading.Lock()


def load(store=None, now=time.monotonic, today: date | None = None) -> PlayerData:
    """The nightly datasets as PlayerData; empty when they were never produced."""
    global _cache
    with _lock:
        if _cache and now() - _cache[0] < CACHE_SECONDS:
            return _cache[1]
    try:
        if store is None:
            from ..ingest.sinks.datasets import build_dataset_store

            store = build_dataset_store()
        injuries = store.get("injuries") or {}
        ownership = store.get("ownership") or {}
        stats = store.get(f"player_stats_{current_season(today)}") or {}
        data = PlayerData(injuries.get("players"), ownership.get("players"), stats,
                          injuries.get("as_of"), ownership.get("as_of"))
    except Exception as e:
        logger.warning("Player datasets unavailable: %s", e)
        data = PlayerData.empty()
    with _lock:
        _cache = (now(), data)
    return data


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None
