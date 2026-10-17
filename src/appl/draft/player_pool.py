"""
Draft player pool: per-game lines blended from last season, ESPN's fantasy projection for
the coming season and the season before, in that order of trust (see CASE_WEIGHTS), plus
the games each player is expected to play.

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
LAST_SEASON = previous_season(DRAFT_SEASON, 1)
PRIOR_SEASON = previous_season(DRAFT_SEASON, 2)
# (season, weight) of the old history-only blend, kept as the backtest baseline
SOURCE_SEASONS = [(LAST_SEASON, 0.7), (PRIOR_SEASON, 0.3)]
# A season's weight is scaled down when it has fewer games than this (old blend)
FULL_SAMPLE_GAMES = 50

# A season with fewer games is too small a sample to use for per-game stats
MIN_SAMPLE_GAMES = 30
MAX_GAMES = 82
# Weights of (last season, ESPN projection, the season before) per history case. A
# source the player lacks is dropped and the rest are rescaled to sum to 1.
CASE_WEIGHTS = {
    "two_seasons": (0.50, 0.35, 0.15),   # both seasons have a real sample
    "last_season": (0.60, 0.40, 0.0),    # only last season does (sophomores, short years)
    "prior_season": (0.0, 0.65, 0.35),   # only the season before (hurt or away last year)
    "projection": (0.0, 1.0, 0.0),       # neither (rookies, small samples)
}
# Same order for projected games; every season counts here, even a short one
GAMES_WEIGHTS = (0.50, 0.35, 0.15)

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
    """The old history-only blend, kept as the backtest baseline (the pool now uses
    blend_sources). Blends per-game stats across seasons, weighting each season by its
    configured weight and by how many games the player actually played.

    Games played (the durability factor) blend with the plain season weights, from
    the newest season back to the player's oldest one: a season he missed counts as
    0 games, while seasons before his debut don't count at all. So a star hurt last
    season keeps part of his healthy year instead of falling out of the pool. It is
    never below the newest season's games, so older seasons can only help."""
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
        debut = max(i for i, (stats, _) in enumerate(seasons) if pid in stats)
        counted = seasons[: debut + 1]
        games = sum(stats[pid]["GP"] * w for stats, w in counted if pid in stats)
        last_season_games = seasons[0][0].get(pid, {}).get("GP", 0)
        player = {
            "nba_id": pid,
            "name": latest["name"],
            "team": latest["team"],
            # Listed position from the newest season that has one
            "pos": next((stats.get("pos") for stats, _ in entries if stats.get("pos")), None),
            "GP": max(round(games / sum(w for _, w in counted), 1), last_season_games),
        }
        for field in STAT_FIELDS:
            player[field] = round(
                sum(stats[field] * w for stats, w in entries) / total_weight, 3
            )
        pool.append(player)
    return pool


def add_projections(pool: list[dict], projections: dict[int, dict]) -> list[dict]:
    """The pool plus a row for every projected player it has no row for, matched by
    id and by name. Rows the history covers are kept as they are; added rows are
    marked "projected" so the app can say the numbers are a projection."""
    ids = {p["nba_id"] for p in pool}
    names = {normalize_name(p["name"]) for p in pool}
    added = []
    for pid, line in projections.items():
        key = normalize_name(line["name"])
        if pid in ids or key in names or line["GP"] <= 0:
            continue
        names.add(key)
        added.append({"nba_id": pid, **{k: line.get(k) for k in ("name", "team", "pos")},
                      "GP": line["GP"], **{f: line[f] for f in STAT_FIELDS},
                      "projected": True})
    if added:
        logger.info(f"Added {len(added)} projected players: "
                    + ", ".join(p["name"] for p in added[:10]))
    return pool + added


def _weighted(values: list[tuple[float | None, float]]) -> float | None:
    """Weighted mean over the values that exist, weights rescaled to sum to 1."""
    present = [(v, w) for v, w in values if v is not None and w]
    total = sum(w for _, w in present)
    return sum(v * w for v, w in present) / total if total else None


def blend_player(pid: int, last: dict | None, prior: dict | None,
                 projection: dict | None) -> dict | None:
    """One pool row from a player's last season, the season before and ESPN's
    projection (any may be None). Stats only use seasons with MIN_SAMPLE_GAMES; games
    use everything. None when there is nothing usable to rank him on."""
    last, prior, projection = (line if line and line["GP"] > 0 else None
                               for line in (last, prior, projection))
    usable = [line is not None and line["GP"] >= MIN_SAMPLE_GAMES for line in (last, prior)]
    basis = ("two_seasons" if all(usable) else "last_season" if usable[0]
             else "prior_season" if usable[1] else "projection")
    sources = [(line, w) for line, w in zip((last, projection, prior), CASE_WEIGHTS[basis])
               if line is not None and w]
    if not sources:
        # Small samples and no projection: pool the seasons if together they're enough
        short = [line for line in (last, prior) if line]
        if sum(line["GP"] for line in short) < MIN_SAMPLE_GAMES:
            return None
        basis, sources = "pooled", [(line, line["GP"]) for line in short]

    # A season missed after his debut counts as 0 games; seasons before it don't count
    last_games = last["GP"] if last else (0 if prior else None)
    games = _weighted(list(zip(
        (last_games, projection and projection["GP"], prior and prior["GP"]), GAMES_WEIGHTS)))
    newest = last or prior or projection
    row = {
        "nba_id": pid,
        "name": newest["name"],
        "team": newest.get("team"),
        "pos": next((line.get("pos") for line in (last, prior, projection)
                     if line and line.get("pos")), None),
        "GP": round(min(games, MAX_GAMES), 1),
        "GP_history": {"last": last_games, "projection": projection and projection["GP"],
                       "prior": prior and prior["GP"]},
        "basis": basis,
    }
    for field in STAT_FIELDS:
        row[field] = round(_weighted([(line[field], w) for line, w in sources]), 3)
    if basis == "projection":
        row["projected"] = True
    return row


def blend_sources(last: dict[int, dict], prior: dict[int, dict],
                  projections: dict[int, dict] | None = None) -> list[dict]:
    """The draft pool from {id: per-game line} for last season, the season before and
    ESPN's projections for the coming one. Projections are matched to history by id,
    then by name (ESPN and NBA ids can differ)."""
    projections = projections or {}
    projection_by_name = {normalize_name(line["name"]): pid for pid, line in projections.items()}
    pool, matched, names = [], set(), set()
    for pid in last.keys() | prior.keys():
        name = normalize_name((last.get(pid) or prior[pid])["name"])
        names.add(name)
        proj_id = pid if pid in projections else projection_by_name.get(name)
        matched.add(proj_id)
        row = blend_player(pid, last.get(pid), prior.get(pid), projections.get(proj_id))
        if row:
            pool.append(row)

    rookies = 0
    for pid, line in projections.items():
        name = normalize_name(line["name"])
        if pid in matched or name in names:
            continue
        names.add(name)
        row = blend_player(pid, None, None, line)
        if row:
            pool.append(row)
            rookies += 1
    if rookies:
        logger.info(f"Added {rookies} players from projections alone")
    return pool


def _fetch_projections(season: str) -> dict[int, dict]:
    return EspnSource().projections(season)


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
    """Fetch and blend the sources, and store the result (the ingest job's step)."""
    logger.info(f"Building draft player pool from {LAST_SEASON}, {DRAFT_SEASON} projections "
                f"and {PRIOR_SEASON}")
    try:
        projections = _fetch_projections(DRAFT_SEASON)
    except Exception as e:
        logger.warning(f"{DRAFT_SEASON}: ESPN projections unavailable ({e}); "
                       "using history only, and the pool has no rookies")
        projections = {}
    pool = blend_sources(_fetch_season(LAST_SEASON), _fetch_season(PRIOR_SEASON), projections)
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
