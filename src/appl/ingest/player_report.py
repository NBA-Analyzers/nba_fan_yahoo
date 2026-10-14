"""The per-player stats report indexed for the AI assistant: season and last-season
averages plus last 30/14/7-day averages. Built from three league-wide tables (this season,
last season, recent game logs) instead of ~1,500 per-player requests."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Optional

SEASON_FIELDS = ["GP", "FGM", "FGA", "FG_PCT", "FTA", "FTM", "FT_PCT", "FG3M",
                 "PTS", "REB", "AST", "STL", "BLK", "TOV", "MIN"]
WINDOW_FIELDS = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "FG_PCT", "FT_PCT", "FG3M",
                 "FGM", "FGA", "FTM", "FTA"]
WINDOWS = {"last_30_days": 30, "last_14_days": 14, "last_7_days": 7}
LOOKBACK_DAYS = max(WINDOWS.values())

FRIENDLY_FIELD_NAMES = {
    "GP": "Games Played", "FGM": "Field Goals Made", "FGA": "Field Goals Attempted",
    "FG_PCT": "Field Goal Percentage", "FTA": "Free Throws Attempted",
    "FTM": "Free Throws Made", "FT_PCT": "Free Throw Percentage", "FG3M": "3PT Made",
    "PTS": "Points", "REB": "Rebounds", "AST": "Assists", "STL": "Steals",
    "BLK": "Blocks", "TOV": "Turnovers", "MIN": "Minutes",
    "GAMES_PLAYED": "Games Played", "AVG_MIN": "Average Minutes",
}


def _friendly(stats: Optional[dict]) -> Optional[dict]:
    if stats is None:
        return None
    return {FRIENDLY_FIELD_NAMES.get(k, k): v for k, v in stats.items()}


def _season_stats(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return _friendly({f: row[f] for f in SEASON_FIELDS if f in row})


def _game_date(value) -> date:
    return datetime.fromisoformat(str(value)[:10]).date()


def _avg(values) -> Optional[float]:
    values = [float(v) for v in values if v is not None]
    return round(mean(values), 2) if values else None


def _window_stats(games: list[dict], today: date, days: int) -> Optional[dict]:
    cutoff = today - timedelta(days=days)
    window = [g for g in games if _game_date(g["GAME_DATE"]) >= cutoff]
    if not window:
        return None
    stats = {"GAMES_PLAYED": len(window), "AVG_MIN": _avg(g.get("MIN") for g in window)}
    for field in WINDOW_FIELDS:
        stats[field] = _avg(g.get(field) for g in window)
    return _friendly(stats)


def build_player_report(current: list[dict], last: list[dict], game_logs: list[dict],
                        today: date) -> dict[str, dict]:
    """{player name: {season, last_season, last_30_days, last_14_days, last_7_days}} for
    everyone with stats this season or last."""
    cur = {r["PLAYER_ID"]: r for r in current}
    prev = {r["PLAYER_ID"]: r for r in last}
    logs: dict[int, list[dict]] = defaultdict(list)
    for g in game_logs:
        logs[g["PLAYER_ID"]].append(g)

    report = {}
    for pid in sorted(cur.keys() | prev.keys(), key=lambda p: (cur.get(p) or prev[p])["PLAYER_NAME"]):
        name = (cur.get(pid) or prev[pid])["PLAYER_NAME"]
        report[name] = {
            "season": _season_stats(cur.get(pid)),
            "last_season": _season_stats(prev.get(pid)),
            **{key: _window_stats(logs.get(pid, []), today, days) for key, days in WINDOWS.items()},
        }
    return report
