"""
Rebuild data/schedule/NBA_schedule.json for the coming NBA season.

Reads ESPN's public scoreboard (stats.nba.com and cdn.nba.com refuse cloud and
scripted requests) one day at a time, keeps regular-season games, and writes
{"YYYY-MM-DD": [{"home_team", "away_team", "game_id"}]} with dates in US Eastern
time, which is how NBA game days are counted.

Run from the repo root:  python src/appl/scripts/schedule/refresh_schedule.py [season_start_year]
With no year it uses this year when run in or after July, otherwise last year's.
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

APPL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APPL.parent))

from appl.season.schedule import SCHEDULE_FILE, TEAMS, team_code  # noqa: E402

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
EASTERN = ZoneInfo("America/New_York")
REGULAR_SEASON = 2
MIN_GAMES = 1000  # a full season has 1230; fewer means the fetch is incomplete


def season_start_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def fetch_day(day: date) -> list[dict]:
    params = {"dates": f"{day:%Y%m%d}", "limit": 200}  # ESPN rejects date ranges
    for attempt in range(3):
        try:
            response = requests.get(URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get("events", [])
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def to_game(event: dict) -> tuple[str, dict] | None:
    """(eastern date, game) for a regular-season event, or None."""
    if event.get("season", {}).get("type") != REGULAR_SEASON:
        return None
    sides = {c.get("homeAway"): team_code(c["team"].get("abbreviation")) or team_code(c["team"].get("displayName"))
             for c in event["competitions"][0]["competitors"]}
    if not sides.get("home") or not sides.get("away"):
        return None
    when = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone(EASTERN)
    return when.date().isoformat(), {
        "home_team": TEAMS[sides["home"]],
        "away_team": TEAMS[sides["away"]],
        "game_id": event["id"],
    }


def build(year: int) -> dict[str, list[dict]]:
    schedule: dict[str, dict[str, dict]] = {}
    day, last = date(year, 10, 1), date(year + 1, 4, 30)
    while day <= last:
        print(f"Fetching {day}...", end="\r")
        for event in fetch_day(day):
            found = to_game(event)
            if found:
                schedule.setdefault(found[0], {})[found[1]["game_id"]] = found[1]
        day += timedelta(days=1)
        time.sleep(0.2)
    return {d: list(schedule[d].values()) for d in sorted(schedule)}


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else season_start_year()
    schedule = build(year)
    total = sum(len(games) for games in schedule.values())
    print(f"\n{total} regular-season games on {len(schedule)} days ({min(schedule, default='-')} to {max(schedule, default='-')})")
    if total < MIN_GAMES:
        print(f"Fewer than {MIN_GAMES} games; keeping the existing schedule file.")
        return 1
    SCHEDULE_FILE.write_text(json.dumps(schedule, indent=4), encoding="utf-8")
    print(f"Saved {SCHEDULE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
