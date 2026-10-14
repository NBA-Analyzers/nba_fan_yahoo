import logging
from typing import Any, Dict, Optional

import yahoo_fantasy_api as yfa
from ...i_sync_league import SyncLeagueData
from ....ingest.http import with_retry
from ....ingest.schemas import Matchup, validate_rows
from ....storage.blob_storage import BlobStorage

logger = logging.getLogger(__name__)
STAT_ID_TO_NAME = {
    "5": "Field Goal Percentage (FG%)",
    "8": "Free Throw Percentage (FT%)",
    "10": "3-Point Field Goals Made (3PTM)",
    "12": "Points",
    "15": "Rebounds",
    "16": "Assists",
    "17": "Steals",
    "18": "Blocks",
    "19": "Turnovers",
    "9004003": "Field Goals Made/Attempted (FGM/FGA)",
    "9007006": "Free Throws Made/Attempted (FTM/FTA)",
}
# Without these the league index is useless, so the sync doesn't count as fresh
CRITICAL = ("league_settings", "standings", "team_rosters")
DEFAULT_END_WEEK = 20


def _points(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _team_from(team_info: list) -> dict:
    metadata = team_info[0]
    extra = team_info[1] if len(team_info) > 1 else {}
    stats = extra.get("team_stats", {}).get("stats", [])
    return {
        "team_name": next((d.get("name") for d in metadata if "name" in d), None),
        "team_key": next((d.get("team_key") for d in metadata if "team_key" in d), None),
        "score": extra.get("team_points", {}).get("total"),
        # Leagues can score categories we don't have a label for; keep them by id
        "stats": {
            STAT_ID_TO_NAME.get(str(s["stat"]["stat_id"]), f"stat_{s['stat']['stat_id']}"):
                s["stat"].get("value")
            for s in stats
        },
    }


def parse_matchups(parsed: dict) -> list[dict]:
    """One week of Yahoo scoreboard matchups -> [{week, team_1, team_2, team_win_name, ...}]."""
    matchups = []
    for key, matchup_wrap in parsed.items():
        if key == "count":
            continue
        matchup = matchup_wrap.get("matchup", {})
        week = matchup.get("week")
        teams = matchup.get("0", {}).get("teams", {})
        team_data = [
            {"week": week, **_team_from(teams[i]["team"])}
            for i in ("0", "1")
            if teams.get(i, {}).get("team")
        ]
        if len(team_data) != 2:
            logger.warning("week %s: matchup with %d team(s) skipped", week, len(team_data))
            continue

        winner = None
        if matchup.get("is_tied") in (1, "1"):
            winner = None
        elif matchup.get("winner_team_key"):
            winner = next((t for t in team_data if t["team_key"] == matchup["winner_team_key"]), None)
        else:
            a, b = _points(team_data[0]["score"]), _points(team_data[1]["score"])
            if a is not None and b is not None and a != b:
                winner = team_data[0] if a > b else team_data[1]

        matchups.append({
            "week": week,
            "team_1": team_data[0],
            "team_2": team_data[1],
            "team_win_name": winner["team_name"] if winner else "Finished in a draw",
            "team_win_score": winner["score"] if winner else team_data[0]["score"],
        })

    validate_rows(Matchup, (
        {"week": m["week"], "teams": [m["team_1"]["team_name"], m["team_2"]["team_name"]],
         "winner": m["team_win_name"]} for m in matchups
    ), source="yahoo matchups")
    return matchups


class YahooLeague(SyncLeagueData):
    def __init__(self, league: yfa.League, sleep=None):
        self.league = league
        self._retry_kwargs = {"sleep": sleep} if sleep else {}
        self.failed: list[str] = []

    def _call(self, label: str, fn):
        return with_retry(fn, attempts=3, delay=1.0, label=f"yahoo {label}", **self._retry_kwargs)

    def _league_setting(self):
        return self._call("settings", self.league.settings)

    def _standings(self):
        return self._call("standings", self.league.standings)

    def _matchups(self, start_week, end_week):
        matchup_data = []
        for week in range(start_week, end_week + 1):
            raw = self._call(f"matchups w{week}", lambda: self.league.matchups(week))
            week_matchups = raw["fantasy_content"]["league"][1]["scoreboard"]["0"]
            matchup_data.append(parse_matchups(week_matchups["matchups"]))
        return matchup_data

    def _free_agents(self, position: str = "Util") -> Dict[str, Any]:
        return self._call("free agents", lambda: self.league.free_agents(position))

    def _team_current_roster(self) -> Dict[str, Any]:
        teams = self._call("teams", self.league.teams)
        return {
            info.get("name", "Unknown Team"):
                self._call(f"roster {key}", lambda key=key: self.league.to_team(key).roster())
            for key, info in teams.items()
        }

    def _weeks(self, settings: Optional[dict]) -> tuple[int, int]:
        """Matchup weeks from the league's own settings, up to the current week."""
        settings = settings or {}
        start = int(settings.get("start_week") or 1)
        end = int(settings.get("end_week") or DEFAULT_END_WEEK)
        try:
            end = min(end, int(self.league.current_week()))
        except Exception:
            pass
        return start, end

    def sync_full_league(self, blob_storage: BlobStorage) -> Dict[str, Any]:
        """Fetch every part of the league and archive each one. A part that fails is
        logged, listed in `self.failed`, and left out; the others still sync.

        Returns {part name: data} for the parts that synced.
        """
        results: Dict[str, Any] = {}
        directory_name = self.league.league_id
        self.failed = []

        def part(name: str, fetch):
            try:
                data = fetch()
            except Exception as e:
                logger.error("League %s: %s failed: %s", directory_name, name, e)
                self.failed.append(name)
                return
            if blob_storage.upload_json_with_retries(data, f"{directory_name}/{name}.json"):
                results[name] = data
            else:
                self.failed.append(name)

        part("league_settings", self._league_setting)
        part("standings", self._standings)
        start, end = self._weeks(results.get("league_settings"))
        part("matchups", lambda: self._matchups(start, end))
        part("free_agents", self._free_agents)
        part("team_rosters", self._team_current_roster)

        logger.info("League %s sync complete: %d ok, failed: %s",
                    directory_name, len(results), self.failed or "none")
        return results

    @property
    def critical_ok(self) -> bool:
        return not any(name in self.failed for name in CRITICAL)
