"""
Draft player pool: blended per-game averages from the last two NBA seasons.

Per-game stats come from ESPN's public stats feed (a few paged requests for
all players), falling back to nba_api if ESPN fails. stats.nba.com blocks some
networks, which is why ESPN is tried first. The blended pool is cached to
data/draft/player_pool_<draft_season>.json so draft night never waits on a
stats API.

Refresh before the draft:  python -m appl.draft.player_pool   (from src/)
"""

import json
import logging
import re
import time
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

POOL_DIR = Path(__file__).resolve().parent.parent / "data" / "draft"

DRAFT_SEASON = "2026-27"
# (season, weight) - most recent season counts most
SOURCE_SEASONS = [("2025-26", 0.7), ("2024-25", 0.3)]
# A season's weight is scaled down when it has fewer games than this
FULL_SAMPLE_GAMES = 50

ESPN_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/"
    "statistics/byathlete"
)
ESPN_PAGE_SIZE = 100
ESPN_TIMEOUT_SECONDS = 30

FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_SECONDS = 90

STAT_FIELDS = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M",
               "FGM", "FGA", "FTM", "FTA"]

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """Normalize a player name so Yahoo and NBA spellings match
    (accents, punctuation, Jr./III suffixes)."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    tokens = re.sub(r"[^a-z ]", "", ascii_name.lower().replace("-", " ")).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)


def _espn_season_year(season: str) -> int:
    """ESPN labels a season by the year it ends: '2025-26' -> 2026."""
    return int(season.split("-")[0]) + 1


def parse_espn_athletes(payload: dict) -> dict[int, dict]:
    """Turn one page of ESPN's byathlete response into per-game stat lines."""
    players = {}
    names = {c["name"]: c["names"] for c in payload.get("categories", [])}
    for row in payload.get("athletes", []):
        stats = {}
        for category in row.get("categories", []):
            stats.update(zip(names.get(category["name"], []), category["values"]))
        athlete = row["athlete"]
        try:
            players[int(athlete["id"])] = {
                "name": athlete["displayName"],
                "team": athlete.get("teamShortName"),
                "pos": (athlete.get("position") or {}).get("abbreviation"),
                "GP": float(stats["gamesPlayed"]),
                "MIN": float(stats["avgMinutes"]),
                "PTS": float(stats["avgPoints"]),
                "REB": float(stats["avgRebounds"]),
                "AST": float(stats["avgAssists"]),
                "STL": float(stats["avgSteals"]),
                "BLK": float(stats["avgBlocks"]),
                "TOV": float(stats["avgTurnovers"]),
                "FG3M": float(stats["avgThreePointFieldGoalsMade"]),
                "FGM": float(stats["avgFieldGoalsMade"]),
                "FGA": float(stats["avgFieldGoalsAttempted"]),
                "FTM": float(stats["avgFreeThrowsMade"]),
                "FTA": float(stats["avgFreeThrowsAttempted"]),
            }
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Skipping ESPN row without full stats: {athlete.get('displayName')}")
    return players


def _fetch_season_espn(season: str) -> dict[int, dict]:
    import requests

    players: dict[int, dict] = {}
    page, pages = 1, 1
    while page <= pages:
        response = requests.get(
            ESPN_URL,
            params={
                "region": "us", "lang": "en", "contentorigin": "espn",
                "isqualified": "false", "page": page, "limit": ESPN_PAGE_SIZE,
                "sort": "offensive.avgPoints:desc",
                "season": _espn_season_year(season), "seasontype": 2,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=ESPN_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        pages = int(payload["pagination"]["pages"])
        players.update(parse_espn_athletes(payload))
        page += 1
    if not players:
        raise RuntimeError(f"ESPN returned no players for {season}")
    return players


def _fetch_season_nba_api(season: str) -> dict[int, dict]:
    from nba_api.stats.endpoints import leaguedashplayerstats

    # stats.nba.com is slow and flaky; retry before giving up
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            df = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star="Regular Season",
                per_mode_detailed="PerGame",
                timeout=FETCH_TIMEOUT_SECONDS,
            ).get_data_frames()[0]
            break
        except Exception as e:
            logger.warning(f"{season}: attempt {attempt}/{FETCH_ATTEMPTS} failed: {e}")
            if attempt == FETCH_ATTEMPTS:
                raise
            time.sleep(2 * attempt)

    players = {}
    for row in df.to_dict("records"):
        players[int(row["PLAYER_ID"])] = {
            "name": row["PLAYER_NAME"],
            "team": row["TEAM_ABBREVIATION"],
            "GP": float(row["GP"]),
            **{field: float(row[field] or 0.0) for field in STAT_FIELDS},
        }
    return players


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


def load_player_pool(refresh: bool = False) -> list[dict]:
    """Return the cached blended pool, fetching it from nba_api if needed."""
    cache_file = POOL_DIR / f"player_pool_{DRAFT_SEASON}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text(encoding="utf-8"))

    logger.info(f"Building draft player pool from {SOURCE_SEASONS}")
    pool = blend_seasons(
        [(_fetch_season(season), weight) for season, weight in SOURCE_SEASONS]
    )
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(pool, indent=2), encoding="utf-8")
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


def load_inseason_pool(today: str | None = None, fetch=None) -> list[dict]:
    """The preseason pool blended with this season's stats so far, rebuilt once a
    day (cached in memory and in data/draft). Falls back to the preseason pool when
    the season hasn't started or the stats feeds are down."""
    global _retry_at
    today = today or time.strftime("%Y-%m-%d")
    if today in _inseason:
        return _inseason[today]

    cache_file = POOL_DIR / f"player_pool_inseason_{today}.json"
    if cache_file.exists():
        pool = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        prior = load_player_pool()
        if time.monotonic() < _retry_at:
            return prior
        try:
            current = (fetch or _fetch_season)(DRAFT_SEASON)
        except Exception as e:
            logger.warning(f"{DRAFT_SEASON}: current stats unavailable ({e}); using the preseason pool")
            current = {}
        if not any(p["GP"] > 0 for p in current.values()):
            # Season not started or feeds down: don't ask again on every request
            _retry_at = time.monotonic() + INSEASON_RETRY_SECONDS
            return prior
        pool = blend_current(prior, current)
        try:
            POOL_DIR.mkdir(parents=True, exist_ok=True)
            for old in POOL_DIR.glob("player_pool_inseason_*.json"):
                old.unlink(missing_ok=True)
            cache_file.write_text(json.dumps(pool), encoding="utf-8")
        except OSError as e:
            logger.warning(f"Couldn't cache the in-season pool: {e}")
    _inseason.clear()
    _inseason[today] = pool
    return pool


if __name__ == "__main__":
    players = load_player_pool(refresh=True)
    print(f"Saved {len(players)} players -> {POOL_DIR}")
