"""
Who plays when. Reads the saved NBA schedule (date -> games) and answers, for a
team, how many games it has in a window and how many are on back-to-back days.
Pure apart from loading the file; teams may be given as abbreviation or full name.
"""

import json
from datetime import date, timedelta
from pathlib import Path

SCHEDULE_FILE = Path(__file__).resolve().parent.parent / "data" / "schedule" / "NBA_schedule.json"
WINDOW_DAYS = 7

TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors", "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}
_FULL_TO_ABBR = {name.lower(): abbr for abbr, name in TEAMS.items()}
_ALIASES = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX", "GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"}


def team_code(team: str | None) -> str | None:
    """Abbreviation for a team given as abbreviation or full name, else None."""
    if not team:
        return None
    text = team.strip()
    code = _ALIASES.get(text.upper(), text.upper())
    return code if code in TEAMS else _FULL_TO_ABBR.get(text.lower())


class Schedule:
    def __init__(self, games_by_date: dict[str, list[dict]]):
        self._days: dict[date, set[str]] = {}
        for day, games in games_by_date.items():
            playing = set()
            for game in games:
                for side in ("home_team", "away_team"):
                    code = team_code(game.get(side))
                    if code:
                        playing.add(code)
            self._days[date.fromisoformat(day)] = playing

    @classmethod
    def load(cls, path: Path = SCHEDULE_FILE) -> "Schedule":
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls({})

    def covers(self, start: date, days: int = WINDOW_DAYS) -> bool:
        """True when the file has games for at least part of the window."""
        return any(start + timedelta(d) in self._days for d in range(days))

    def dates(self, team: str | None, start: date, days: int = WINDOW_DAYS) -> list[date]:
        code = team_code(team)
        return [
            start + timedelta(d) for d in range(days)
            if code and code in self._days.get(start + timedelta(d), ())
        ]

    def games(self, team: str | None, start: date, days: int = WINDOW_DAYS) -> int:
        return len(self.dates(team, start, days))

    def back_to_backs(self, team: str | None, start: date, days: int = WINDOW_DAYS) -> int:
        played = self.dates(team, start, days)
        return sum(1 for a, b in zip(played, played[1:]) if (b - a).days == 1)
