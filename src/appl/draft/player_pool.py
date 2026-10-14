"""
Draft player pool: blended per-game averages from the last two NBA seasons.

Per-game stats come from ESPN's public stats feed (a few paged requests for
all players), falling back to nba_api if ESPN fails. stats.nba.com blocks some
networks, which is why ESPN is tried first. Both fetchers live in appl/ingest/sources.

The blended pool is stored as a dataset (GCS on Cloud Run, data/draft locally) by the
nightly ingest job, so draft night never waits on a stats API. The committed
data/draft/player_pool_<season>.json is the fallback a fresh deploy starts from.

Refresh by hand:  python -m appl.ingest run player_pool   (from src/)
"""

import json
import logging
import os
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

from ..ingest.season import current_season, previous_season
from ..ingest.sinks.datasets import LocalDatasetStore, build_dataset_store
from ..ingest.sources.espn import EspnSource, espn_season_year, parse_espn_athletes  # noqa: F401
from ..ingest.sources.nba import STAT_FIELDS, NbaSource

logger = logging.getLogger(__name__)

POOL_DIR = Path(__file__).resolve().parent.parent / "data" / "draft"

# The season being drafted / played; rolls over every July
DRAFT_SEASON = current_season()
# (season, weight) - most recent season counts most
SOURCE_SEASONS = [(previous_season(DRAFT_SEASON, 1), 0.7), (previous_season(DRAFT_SEASON, 2), 0.3)]
# A season's weight is scaled down when it has fewer games than this
FULL_SAMPLE_GAMES = 50

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _store():
    """GCS when a bucket is configured, otherwise files in POOL_DIR."""
    if os.environ.get("DATASET_BUCKET") or os.environ.get("GCS_BUCKET"):
        return build_dataset_store()
    return LocalDatasetStore(POOL_DIR)


def normalize_name(name: str) -> str:
    """Normalize a player name so Yahoo and NBA spellings match
    (accents, punctuation, Jr./III suffixes)."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    tokens = re.sub(r"[^a-z ]", "", ascii_name.lower().replace("-", " ")).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)


_espn_season_year = espn_season_year


def _fetch_season_espn(season: str) -> dict[int, dict]:
    return EspnSource().season(season)


def _fetch_season_nba_api(season: str) -> dict[int, dict]:
    return NbaSource().season_lines(season)


def blend_seasons(seasons: list[tuple[dict[int, dict], float]]) -> list[dict]:
    """Blend per-game stats across seasons, weighting each season by its
    configured weight and by how many games the player actually played."""
    player_ids = {pid for stats, _ in seasons for pid in stats}
    pool = []
    for pid in player_ids:
        entries = [
            (stats[pid], weight * min(stats[pid]["GP"] / FULL_SAMPLE_GAMES, 1.0))
            for stats, weight in seasons
            if pid in stats and stats[pid]["GP"] > 0
        ]
        total_weight = sum(w for _, w in entries)
        if not total_weight:
            continue

        latest = entries[0][0]
        player = {
            "nba_id": pid,
            "name": latest["name"],
            "team": latest["team"],
            # Listed position from the newest season that has one
            "pos": next((stats.get("pos") for stats, _ in entries if stats.get("pos")), None),
            # Most recent season's games played drives the durability factor
            "GP": latest["GP"],
        }
        for field in STAT_FIELDS:
            player[field] = round(
                sum(stats[field] * w for stats, w in entries) / total_weight, 3
            )
        pool.append(player)
    return pool


def _fetch_season(season: str) -> dict[int, dict]:
    """ESPN first (reachable from more networks), nba_api as the fallback."""
    try:
        return _fetch_season_espn(season)
    except Exception as e:
        logger.warning(f"{season}: ESPN failed ({e}); trying nba_api")
        return _fetch_season_nba_api(season)


POOL_TTL_SECONDS = 60 * 60
_preseason: dict[str, tuple[float, list[dict]]] = {}


def build_player_pool() -> list[dict]:
    """Fetch and blend the source seasons, and store the result (the ingest job's step)."""
    logger.info(f"Building draft player pool from {SOURCE_SEASONS}")
    pool = blend_seasons(
        [(_fetch_season(season), weight) for season, weight in SOURCE_SEASONS]
    )
    _store().put(f"player_pool_{DRAFT_SEASON}", pool)
    _preseason[DRAFT_SEASON] = (time.monotonic(), pool)
    return pool


def load_player_pool(refresh: bool = False) -> list[dict]:
    """The blended pool: memory (1h) -> dataset store -> committed file -> fetch now."""
    if refresh:
        return build_player_pool()
    cached = _preseason.get(DRAFT_SEASON)
    if cached and time.monotonic() - cached[0] < POOL_TTL_SECONDS:
        return cached[1]

    name = f"player_pool_{DRAFT_SEASON}"
    pool = _store().get(name)
    if pool is None:
        committed = POOL_DIR / f"{name}.json"
        if committed.exists():
            pool = json.loads(committed.read_text(encoding="utf-8"))
    if pool is None:
        return build_player_pool()
    _preseason[DRAFT_SEASON] = (time.monotonic(), pool)
    return pool


# --- in season ----------------------------------------------------------------

# This season's games count as much as the prior pool after this many games
CURRENT_SEASON_PRIOR_GAMES = 15
FULL_SEASON_GP = 70
INSEASON_RETRY_SECONDS = 30 * 60
_inseason: dict[str, list[dict]] = {}
_retry_at = 0.0


def blend_current(prior: list[dict], current: dict[int, dict]) -> list[dict]:
    """The preseason pool updated with this season's per-game stats. A player's
    current numbers weigh gp / (gp + CURRENT_SEASON_PRIOR_GAMES), so a hot first
    week moves him a little and half a season moves him a lot. Players are matched
    by name, since the two sources may use different ids. Games played are scaled
    to a full season so rookies and early-season players aren't filtered out."""
    most_games = max((p["GP"] for p in current.values()), default=0)
    scale = FULL_SEASON_GP / most_games if most_games else 0.0
    now = {normalize_name(p["name"]): p for p in current.values() if p["GP"] > 0}

    pool, seen = [], set()
    for player in prior:
        key = normalize_name(player["name"])
        cur = now.get(key)
        if not cur:
            pool.append(player)
            continue
        seen.add(key)
        w = cur["GP"] / (cur["GP"] + CURRENT_SEASON_PRIOR_GAMES)
        blended = {**player, "team": cur.get("team") or player["team"],
                   "pos": player.get("pos") or cur.get("pos")}
        for field in STAT_FIELDS:
            blended[field] = round(w * cur[field] + (1 - w) * player[field], 3)
        blended["GP"] = round(w * cur["GP"] * scale + (1 - w) * player["GP"], 1)
        blended["GP_current"] = cur["GP"]
        pool.append(blended)

    for pid, cur in current.items():
        key = normalize_name(cur["name"])
        if key in now and key not in seen:
            # New this season (rookies, returns from injury)
            pool.append({"nba_id": pid, **{k: cur.get(k) for k in ("name", "team", "pos")},
                         "GP": round(cur["GP"] * scale, 1), "GP_current": cur["GP"],
                         **{field: cur[field] for field in STAT_FIELDS}})
    return pool


INSEASON_DATASET = "player_pool_inseason"


def build_inseason_pool(today: str, fetch=None) -> list[dict] | None:
    """Blend this season's stats into the preseason pool and store it. None when the
    season hasn't started or the feeds are down."""
    prior = load_player_pool()
    season = current_season(date.fromisoformat(today))
    try:
        current = (fetch or _fetch_season)(season)
    except Exception as e:
        logger.warning(f"{season}: current stats unavailable ({e}); using the preseason pool")
        return None
    if not any(p["GP"] > 0 for p in current.values()):
        return None
    pool = blend_current(prior, current)
    try:
        _store().put(INSEASON_DATASET, {"date": today, "pool": pool})
    except Exception as e:
        logger.warning(f"Couldn't store the in-season pool: {e}")
    return pool


def load_inseason_pool(today: str | None = None, fetch=None) -> list[dict]:
    """The preseason pool blended with this season's stats so far, rebuilt once a
    day (cached in memory and in the dataset store; the nightly job usually builds it
    first). Falls back to the preseason pool when the season hasn't started or the
    stats feeds are down."""
    global _retry_at
    today = today or time.strftime("%Y-%m-%d")
    if today in _inseason:
        return _inseason[today]

    stored = _store().get(INSEASON_DATASET)
    if stored and stored.get("date") == today:
        pool = stored["pool"]
    else:
        if time.monotonic() < _retry_at:
            return load_player_pool()
        pool = build_inseason_pool(today, fetch)
        if pool is None:
            # Season not started or feeds down: don't ask again on every request
            _retry_at = time.monotonic() + INSEASON_RETRY_SECONDS
            return load_player_pool()
    _inseason.clear()
    _inseason[today] = pool
    return pool


if __name__ == "__main__":
    players = load_player_pool(refresh=True)
    print(f"Saved {len(players)} players")
