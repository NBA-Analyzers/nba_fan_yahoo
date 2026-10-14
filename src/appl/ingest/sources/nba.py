"""stats.nba.com via nba_api. Every call goes through one rate limiter and retry policy,
and league-wide tables are fetched once per run (memoized), never once per player."""

import logging
from datetime import date, timedelta
from typing import Callable, Optional

from ..http import RateLimiter, with_retry
from ..schemas import ScheduledGame, SeasonLine, validate_rows

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 90
STAT_FIELDS = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M",
               "FGM", "FGA", "FTM", "FTA"]


def _scoreboard_cls():
    from nba_api.stats.endpoints import scoreboardv2
    from nba_api.stats.endpoints._base import Endpoint

    class Scoreboard(scoreboardv2.ScoreboardV2):
        """ScoreboardV2 raises KeyError for future dates: 'WinProbability' is missing."""

        def load_response(self):
            data_sets = self.nba_response.get_data_sets()
            self.game_header = Endpoint.DataSet(data=data_sets["GameHeader"])

    return Scoreboard


class NbaSource:
    def __init__(self, limiter: Optional[RateLimiter] = None,
                 sleep: Optional[Callable[[float], None]] = None, api=None):
        self._limiter = limiter or RateLimiter(0.6)
        self._retry_kwargs = {"sleep": sleep} if sleep else {}
        self._api = api  # tests inject a fake with the same methods as _NbaApi
        self._dash: dict[str, list[dict]] = {}
        self._logs: dict[tuple[str, str], list[dict]] = {}

    @property
    def api(self):
        if self._api is None:
            self._api = _NbaApi()
        return self._api

    def _call(self, label: str, fn):
        def call():
            self._limiter.wait()
            return fn()

        return with_retry(call, attempts=3, delay=2.0, label=f"nba_api {label}", **self._retry_kwargs)

    # --- league-wide tables -------------------------------------------------------

    def league_dash(self, season: str) -> list[dict]:
        """Every player's per-game averages for `season` (raw nba_api columns)."""
        if season not in self._dash:
            self._dash[season] = self._call(f"league_dash {season}",
                                            lambda: self.api.league_dash(season))
        return self._dash[season]

    def season_lines(self, season: str) -> dict[int, dict]:
        """{nba_id: per-game line} in the player-pool shape."""
        rows = validate_rows(SeasonLine, (
            {"nba_id": r["PLAYER_ID"], "name": r["PLAYER_NAME"], "team": r.get("TEAM_ABBREVIATION"),
             "GP": r["GP"], **{f: float(r.get(f) or 0.0) for f in STAT_FIELDS}}
            for r in self.league_dash(season)
        ), source=f"nba_api {season}")
        return {r.nba_id: r.model_dump(exclude={"nba_id"}) for r in rows}

    def game_logs(self, season: str, since: date) -> list[dict]:
        """Every player's game lines in `season` from `since` on, in one request."""
        key = (season, since.isoformat())
        if key not in self._logs:
            self._logs[key] = self._call(f"game_logs {season}",
                                         lambda: self.api.game_logs(season, since))
        return self._logs[key]

    # --- schedule --------------------------------------------------------------------

    def schedule(self, start: date, end: date) -> list[dict]:
        """Games from `start` to `end` inclusive, one scoreboard request per day. A day
        that fails after retries is logged and skipped so one bad day can't sink the run."""
        games, seen, failed = [], set(), 0
        day = start
        while day <= end:
            day_str = day.isoformat()
            try:
                rows = self._call(f"scoreboard {day_str}", lambda: self.api.scoreboard(day_str))
            except Exception as e:
                failed += 1
                logger.warning("schedule %s skipped: %s", day_str, type(e).__name__)
                rows = []
            for row in rows:
                if row["game_id"] in seen:
                    continue
                seen.add(row["game_id"])
                games.append({**row, "date": day_str})
            day += timedelta(days=1)
        if failed:
            logger.warning("schedule: %d day(s) could not be fetched", failed)
        return [g.model_dump() for g in validate_rows(ScheduledGame, games, source="schedule")]


class _NbaApi:
    """The real nba_api calls, as plain lists of dicts."""

    def league_dash(self, season: str) -> list[dict]:
        from nba_api.stats.endpoints import leaguedashplayerstats

        return leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, season_type_all_star="Regular Season",
            per_mode_detailed="PerGame", timeout=TIMEOUT_SECONDS,
        ).get_data_frames()[0].to_dict("records")

    def game_logs(self, season: str, since: date) -> list[dict]:
        from nba_api.stats.endpoints import playergamelogs

        return playergamelogs.PlayerGameLogs(
            season_nullable=season, season_type_nullable="Regular Season",
            date_from_nullable=since.strftime("%m/%d/%Y"), timeout=TIMEOUT_SECONDS,
        ).get_data_frames()[0].to_dict("records")

    def scoreboard(self, day: str) -> list[dict]:
        from nba_api.stats.static import teams

        names = {t["id"]: t["full_name"] for t in teams.get_teams()}
        header = _scoreboard_cls()(game_date=day, timeout=TIMEOUT_SECONDS).game_header
        return [
            {"game_id": str(g["GAME_ID"]),
             "home_team": names.get(g["HOME_TEAM_ID"], f"Unknown ({g['HOME_TEAM_ID']})"),
             "away_team": names.get(g["VISITOR_TEAM_ID"], f"Unknown ({g['VISITOR_TEAM_ID']})")}
            for g in header.get_data_frame().to_dict("records")
        ]
