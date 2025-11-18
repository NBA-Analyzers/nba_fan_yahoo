#!/usr/bin/env python3
"""
General NBA player stats utility with fantasy-friendly categories.
Requires: pip install nba_api pandas
"""

from datetime import datetime, timedelta
import json
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog
from nba_api.stats.static import players

NINE_CAT_FIELDS = [
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "FG_PCT",
    "FT_PCT",
    "FG3M",
]
VOLUME_FIELDS = ["FGM", "FGA", "FTM", "FTA"]
ORDERED_SEASON_FIELDS = [
    "GP",
    "FGM",
    "FGA",
    "FG_PCT",
    "FTA",
    "FTM",
    "FT_PCT",
    "FG3M",
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "MIN",
]


def find_player_id(player_name: str):
    """Find a player's ID by full name."""
    matches = players.find_players_by_full_name(player_name)
    if matches:
        return matches[0]["id"], matches[0]["full_name"]
    return None, None


def get_season_stats(player_id, season="2024-25"):
    """Return per-game season averages."""
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",
        )
        df = stats.get_data_frames()[0]
        player_stats = df[df["PLAYER_ID"] == player_id]

        if player_stats.empty:
            return None

        columns = ORDERED_SEASON_FIELDS
        existing_columns = [col for col in columns if col in player_stats.columns]
        return player_stats[existing_columns].iloc[0].to_dict()
    except Exception as e:
        print(f"Error getting season stats: {e}")
        return None


_GAME_LOG_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def _get_cached_gamelog(player_id: str, season: str) -> pd.DataFrame:
    cache_key = (player_id, season)
    if cache_key not in _GAME_LOG_CACHE:
        gamelog = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            season_type_all_star="Regular Season",
        )
        df = gamelog.get_data_frames()[0]
        if not df.empty:
            df = df.copy()
            df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
        _GAME_LOG_CACHE[cache_key] = df
    return _GAME_LOG_CACHE[cache_key]


def _aggregate_period_stats(player_id, season: str, days_back: int):
    """Compute averages for the last `days_back` days using cached gamelog data."""

    df = _get_cached_gamelog(player_id, season)
    if df.empty:
        return None

    cutoff = datetime.now() - timedelta(days=days_back)
    window_df = df[df["GAME_DATE"] >= cutoff]
    if window_df.empty:
        return None

    stats = {"GAMES_PLAYED": len(window_df)}

    avg_min = window_df["MIN"].mean()
    stats["AVG_MIN"] = round(float(avg_min), 2) if pd.notnull(avg_min) else None

    for field in NINE_CAT_FIELDS + VOLUME_FIELDS:
        if field in window_df.columns:
            value = window_df[field].mean()
            stats[field] = round(float(value), 2) if pd.notnull(value) else None

    return stats


def get_monthly_stats(player_id, season="2024-25"):
    """Return averages for the last 30 days."""
    return _aggregate_period_stats(player_id, season, days_back=30)


def get_two_week_stats(player_id, season="2024-25"):
    """Return averages for the last 14 days."""
    return _aggregate_period_stats(player_id, season, days_back=14)


def get_weekly_stats(player_id, season="2024-25"):
    """Return averages for the last 7 days."""
    return _aggregate_period_stats(player_id, season, days_back=7)


def _previous_season(season: str) -> str:
    """Given 'YYYY-YY', return the previous season string."""
    try:
        start_year = int(season.split("-")[0])
        prev_start = start_year - 1
        prev_end = str(prev_start + 1)[-2:]
        return f"{prev_start}-{prev_end}"
    except Exception:
        raise ValueError(f"Invalid season format: {season}. Expected 'YYYY-YY'.")


def build_player_report(
    player_name: str, season: str = "2025-26", player_id_override: int | None = None
):
    """Return a nested dict with all stat views for the player."""
    if player_id_override is not None:
        player_id = player_id_override
        canonical_name = player_name
    else:
        player_id, canonical_name = find_player_id(player_name)
        if not player_id:
            raise ValueError(f"Could not find a player that matches '{player_name}'")

    previous_season = _previous_season(season)

    report = {
        canonical_name: {
            "season": get_season_stats(player_id, season),
            "last_season": get_season_stats(player_id, previous_season),
            "last_30_days": get_monthly_stats(player_id, season),
            "last_14_days": get_two_week_stats(player_id, season),
            "last_7_days": get_weekly_stats(player_id, season),
        }
    }
    return report


def export_report_to_json(report: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def generate_consolidated_player_stats(season: str = "2025-26") -> Path:
    output_dir = Path("player_reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"active_players_{season}.json"

    active_players = players.get_active_players()
    print(f"Found {len(active_players)} active players. Generating reports...")

    consolidated_report: dict[str, dict] = {}

    for player in sorted(active_players, key=lambda p: p["full_name"]):
        player_name = player["full_name"]
        player_id = player["id"]
        try:
            report = build_player_report(
                player_name, season, player_id_override=player_id
            )
            consolidated_report.update(report)
            print(f"Added stats report for {player_name} ({season})")
        except Exception as exc:
            print(f"Failed to build report for {player_name}: {exc}")

    export_report_to_json(consolidated_report, output_file)
    print(f"Saved consolidated stats report -> {output_file}")
    return output_file


def main():
    generate_consolidated_player_stats()


if __name__ == "__main__":
    main()
