"""ESPN's public per-game stats feed: a few paged requests return every player.
Tried before nba_api because stats.nba.com blocks some networks (Cloud Run included)."""

import logging

from ..http import RateLimiter, with_retry
from ..schemas import SeasonLine, validate_rows

logger = logging.getLogger(__name__)

ESPN_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/"
    "statistics/byathlete"
)
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30

_FIELDS = {
    "GP": "gamesPlayed", "MIN": "avgMinutes", "PTS": "avgPoints", "REB": "avgRebounds",
    "AST": "avgAssists", "STL": "avgSteals", "BLK": "avgBlocks", "TOV": "avgTurnovers",
    "FG3M": "avgThreePointFieldGoalsMade", "FGM": "avgFieldGoalsMade",
    "FGA": "avgFieldGoalsAttempted", "FTM": "avgFreeThrowsMade",
    "FTA": "avgFreeThrowsAttempted",
}


def espn_season_year(season: str) -> int:
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
                **{field: float(stats[key]) for field, key in _FIELDS.items()},
            }
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Skipping ESPN row without full stats: {athlete.get('displayName')}")
    return players


class EspnSource:
    def __init__(self, get=None, limiter: RateLimiter | None = None, sleep=None):
        if get is None:
            import requests

            get = requests.get
        self._get = get
        self._limiter = limiter or RateLimiter(0.2)
        self._retry_kwargs = {"sleep": sleep} if sleep else {}

    def _page(self, season: str, page: int) -> dict:
        def call():
            self._limiter.wait()
            response = self._get(
                ESPN_URL,
                params={
                    "region": "us", "lang": "en", "contentorigin": "espn",
                    "isqualified": "false", "page": page, "limit": PAGE_SIZE,
                    "sort": "offensive.avgPoints:desc",
                    "season": espn_season_year(season), "seasontype": 2,
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        return with_retry(call, label=f"ESPN {season} p{page}", **self._retry_kwargs)

    def season(self, season: str) -> dict[int, dict]:
        """{espn_id: per-game line} for every player with stats that season."""
        players: dict[int, dict] = {}
        page, pages = 1, 1
        while page <= pages:
            payload = self._page(season, page)
            pages = int(payload["pagination"]["pages"])
            players.update(parse_espn_athletes(payload))
            page += 1
        if not players:
            raise RuntimeError(f"ESPN returned no players for {season}")
        rows = validate_rows(SeasonLine, ({"nba_id": pid, **p} for pid, p in players.items()),
                             source=f"ESPN {season}")
        return {r.nba_id: r.model_dump(exclude={"nba_id"}) for r in rows}
