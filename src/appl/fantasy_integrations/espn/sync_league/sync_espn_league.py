import logging
from typing import Any, Dict, Optional

from ...i_sync_league import SyncLeagueData
from ....ingest.http import with_retry
from ....ingest.schemas import Matchup, validate_rows
from ....storage.blob_storage import BlobStorage

logger = logging.getLogger(__name__)

# Same rule as Yahoo: without these the league index is useless
CRITICAL = ("league_settings", "standings", "team_rosters")
FREE_AGENTS_LIMIT = 50


def _player(p) -> dict:
    stats = getattr(p, "stats", None)
    return {
        "name": getattr(p, "name", None),
        "position": getattr(p, "position", None),
        "pro_team": getattr(p, "proTeam", None),
        "injury_status": getattr(p, "injuryStatus", None),
        "avg_stats": stats.get("avg") if isinstance(stats, dict) else None,
    }


def _team_name(team) -> str:
    return getattr(team, "team_name", None) or "Unknown Team"


def parse_matchups(week: int, scoreboard: list) -> list[dict]:
    """One week of ESPN scoreboard matchups, in the shape the Yahoo sync produces."""
    matchups = []
    for m in scoreboard:
        home, away = getattr(m, "home_team", None), getattr(m, "away_team", None)
        if not home or not away or isinstance(home, int) or isinstance(away, int):
            continue  # a bye week has no opponent
        winner_flag = getattr(m, "winner", None)
        winner = {"HOME": home, "AWAY": away}.get(winner_flag)
        home_score, away_score = getattr(m, "home_final_score", None), getattr(m, "away_final_score", None)
        matchups.append({
            "week": week,
            "team_1": {"team_name": _team_name(home), "score": home_score},
            "team_2": {"team_name": _team_name(away), "score": away_score},
            "team_win_name": _team_name(winner) if winner else "Finished in a draw"
            if winner_flag == "TIE" else None,
            "team_win_score": (home_score if winner is home else away_score) if winner else home_score,
        })
    return matchups


class EspnLeague(SyncLeagueData):
    """Syncs one ESPN league (an espn_api.basketball.League) under `league_key`, the
    id the chat uses for it, so blobs and the RAG index line up with the Yahoo ones."""

    def __init__(self, league, league_key: str, sleep=None):
        self.league = league
        self.league_key = league_key
        self._retry_kwargs = {"sleep": sleep} if sleep else {}
        self.failed: list[str] = []

    def _call(self, label: str, fn):
        return with_retry(fn, attempts=3, delay=1.0, label=f"espn {label}", **self._retry_kwargs)

    def _league_setting(self):
        settings = self.league.settings
        return {
            "name": getattr(settings, "name", None),
            "num_teams": getattr(settings, "team_count", None) or len(self.league.teams),
            "season": getattr(self.league, "year", None),
            "current_week": getattr(self.league, "currentMatchupPeriod", None),
            "regular_season_matchups": getattr(settings, "reg_season_count", None),
            "playoff_teams": getattr(settings, "playoff_team_count", None),
        }

    def _standings(self):
        return [
            {"rank": i + 1, "team_name": _team_name(t), "wins": getattr(t, "wins", None),
             "losses": getattr(t, "losses", None), "ties": getattr(t, "ties", None)}
            for i, t in enumerate(self._call("standings", self.league.standings))
        ]

    def _matchups(self, start_week, end_week):
        weeks = []
        for week in range(start_week, end_week + 1):
            scoreboard = self._call(f"matchups w{week}", lambda w=week: self.league.scoreboard(w))
            weeks.append(parse_matchups(week, scoreboard))
        validate_rows(Matchup, (
            {"week": m["week"], "teams": [m["team_1"]["team_name"], m["team_2"]["team_name"]],
             "winner": m["team_win_name"]} for week in weeks for m in week
        ), source="espn matchups")
        return weeks

    def _free_agents(self, position: str = "Util") -> Dict[str, Any]:
        players = self._call("free agents", lambda: self.league.free_agents(size=FREE_AGENTS_LIMIT))
        return [_player(p) for p in players]

    def _team_current_roster(self) -> Dict[str, Any]:
        return {_team_name(t): [_player(p) for p in getattr(t, "roster", [])] for t in self.league.teams}

    def _weeks(self) -> tuple[int, int]:
        try:
            return 1, int(self.league.currentMatchupPeriod)
        except (TypeError, ValueError, AttributeError):
            return 1, 0

    def sync_full_league(self, blob_storage: BlobStorage) -> Dict[str, Any]:
        """Same contract as YahooLeague.sync_full_league: {part name: data} for the
        parts that synced; a failed part is logged and listed in `self.failed`."""
        results: Dict[str, Any] = {}
        self.failed = []

        def part(name: str, fetch):
            try:
                data = fetch()
            except Exception as e:
                logger.error("League %s: %s failed: %s", self.league_key, name, e)
                self.failed.append(name)
                return
            if blob_storage.upload_json_with_retries(data, f"{self.league_key}/{name}.json"):
                results[name] = data
            else:
                self.failed.append(name)

        part("league_settings", self._league_setting)
        part("standings", self._standings)
        start, end = self._weeks()
        part("matchups", lambda: self._matchups(start, end))
        part("free_agents", self._free_agents)
        part("team_rosters", self._team_current_roster)

        logger.info("League %s sync complete: %d ok, failed: %s",
                    self.league_key, len(results), self.failed or "none")
        return results

    @property
    def critical_ok(self) -> bool:
        return not any(name in self.failed for name in CRITICAL)
