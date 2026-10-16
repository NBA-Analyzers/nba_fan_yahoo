"""ESPN's public per-game stats feed: a few paged requests return every player.
Tried before nba_api because stats.nba.com blocks some networks (Cloud Run included).

Also ESPN fantasy's preseason projections, which cover players with no recent NBA
stats (rookies, players back from a lost season)."""

import json
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

PROJECTIONS_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}"
    "/segments/0/leaguedefaults/3"
)
PROJECTIONS_LIMIT = 1000  # most-owned players; ESPN projects about 400 of them

# ESPN fantasy stat ids -> pool fields (espn_api.basketball.constant.STATS_MAP)
_PROJECTED_FIELDS = {
    "GP": "42", "MIN": "40", "PTS": "0", "REB": "6", "AST": "3", "STL": "2", "BLK": "1",
    "TOV": "11", "FG3M": "17", "FGM": "13", "FGA": "14", "FTM": "15", "FTA": "16",
}
# ESPN fantasy proTeamId -> the team abbreviations the byathlete feed uses
_PRO_TEAMS = {
    1: "ATL", 2: "BOS", 3: "NO", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GS",
    10: "HOU", 11: "IND", 12: "LAC", 13: "LAL", 14: "MIA", 15: "MIL", 16: "MIN", 17: "BKN",
    18: "NY", 19: "ORL", 20: "PHI", 21: "PHX", 22: "POR", 23: "SAC", 24: "SA", 25: "OKC",
    26: "UTAH", 27: "WSH", 28: "TOR", 29: "MEM", 30: "CHA",
}
# ESPN fantasy defaultPositionId -> the G/F/C the byathlete feed lists
_POSITIONS = {1: "G", 2: "G", 3: "F", 4: "F", 5: "C"}

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


def parse_espn_projections(payload: dict, season_year: int) -> dict[int, dict]:
    """{espn_id: projected per-game line} from ESPN fantasy's player list. Only players
    ESPN projects for `season_year` (the year the season ends) are returned. ESPN leaves
    out stats projected at zero, so a missing stat is 0; games played is required."""
    stat_id = f"10{season_year}"  # statSourceId 1 (projected), split 0 (season), year
    players = {}
    for row in payload.get("players", []) or []:
        player = row.get("player") or {}
        projected = next((s.get("averageStats") for s in player.get("stats") or []
                          if s.get("id") == stat_id), None)
        if not projected or not player.get("fullName"):
            continue
        try:
            players[int(player["id"])] = {
                "name": player["fullName"],
                "team": _PRO_TEAMS.get(player.get("proTeamId")),
                "pos": _POSITIONS.get(player.get("defaultPositionId")),
                "GP": float(projected[_PROJECTED_FIELDS["GP"]]),
                **{field: float(projected.get(key) or 0.0)
                   for field, key in _PROJECTED_FIELDS.items() if field != "GP"},
            }
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Skipping ESPN projection without full stats: {player['fullName']}")
    return players


def _not_started(payload: dict, season: str) -> bool:
    """ESPN's reply for the season it calls current, before any regular-season game:
    no players and no pagination. The same reply for any other season is an error."""
    current = (payload.get("currentSeason") or {}).get("year")
    return ("pagination" not in payload and not payload.get("athletes")
            and current == espn_season_year(season))


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
        """{espn_id: per-game line} for every player with stats that season. Empty when
        the season hasn't started: ESPN then answers with season info and no players."""
        players: dict[int, dict] = {}
        page, pages = 1, 1
        while page <= pages:
            payload = self._page(season, page)
            if page == 1 and _not_started(payload, season):
                logger.info(f"ESPN: {season} hasn't started, no stats yet")
                return {}
            pages = int(payload["pagination"]["pages"])
            players.update(parse_espn_athletes(payload))
            page += 1
        if not players:
            raise RuntimeError(f"ESPN returned no players for {season}")
        rows = validate_rows(SeasonLine, ({"nba_id": pid, **p} for pid, p in players.items()),
                             source=f"ESPN {season}")
        return {r.nba_id: r.model_dump(exclude={"nba_id"}) for r in rows}

    def projections(self, season: str) -> dict[int, dict]:
        """{espn_id: projected per-game line} for `season`, in the player-pool shape."""
        year = espn_season_year(season)
        filters = {"players": {"limit": PROJECTIONS_LIMIT,
                               "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}

        def call():
            self._limiter.wait()
            response = self._get(
                PROJECTIONS_URL.format(year=year), params={"view": "kona_player_info"},
                headers={"User-Agent": "Mozilla/5.0", "X-Fantasy-Filter": json.dumps(filters)},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = with_retry(call, label=f"ESPN projections {season}", **self._retry_kwargs)
        rows = validate_rows(SeasonLine, ({"nba_id": pid, **p} for pid, p in
                                          parse_espn_projections(payload, year).items()),
                             source=f"ESPN projections {season}")
        return {r.nba_id: r.model_dump(exclude={"nba_id"}) for r in rows}
