import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict

import yahoo_fantasy_api as yfa
from ...i_sync_league import SyncLeagueData
from ....repository.azure.azure_blob_storage import AzureBlobStorage

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


class YahooLeague(SyncLeagueData):
    def __init__(self, league: yfa.League):
        self.league = league

    def _league_setting(self):
        return self.league.settings()
        # league_settings_json = json.dumps(self.league.settings(), indent=2)
        # with open("league_settings.json", "w") as f:
        #     f.write(league_settings_json)

    def _standings(self):
        return self.league.standings()
        # standings = json.dumps(self.league.standings(),indent=2)
        # with open("standings.json", "w") as f:
        #     f.write(standings)

    def _extract_matchup_info(self, parsed):
        matchups = []

        for key, matchup_wrap in parsed.items():
            if key == "count":
                continue
            matchup = matchup_wrap.get("matchup", {})
            week = matchup.get("week")
            team_data = []

            for team_index in ["0", "1"]:
                team_info = (
                    matchup.get("0", {})
                    .get("teams", {})
                    .get(team_index, {})
                    .get("team", [])
                )
                if not team_info:
                    continue

                metadata = team_info[0]
                stats = team_info[1].get("team_stats", {}).get("stats", [])
                team_points = team_info[1].get("team_points", {}).get("total", None)

                team = {
                    "week": week,
                    "team_name": next(
                        (d.get("name") for d in metadata if "name" in d), None
                    ),
                    "team_key": next(
                        (d.get("team_key") for d in metadata if "team_key" in d), None
                    ),
                    "score": team_points,
                    "stats": {
                        STAT_ID_TO_NAME[s["stat"]["stat_id"]]: s["stat"]["value"]
                        for s in stats
                    },
                }
                team_data.append(team)

            team_0_score = team_data[0]["score"]
            team_1_score = team_data[1]["score"]
            if team_0_score > team_1_score:
                team_win_name = team_data[0]["team_name"]
                team_win_score = team_data[0]["score"]
            elif team_1_score > team_0_score:
                team_win_name = team_data[0]["team_name"]
                team_win_score = team_data[0]["score"]
            else:
                team_win_name = "Finshed In a Draw"
                team_win_score = team_data[0]["score"]

            stat_winners = 0
            if len(team_data) == 2:
                matchups.append(
                    {
                        "week": week,
                        "team_1": team_data[0],
                        "team_2": team_data[1],
                        "team_win_name": team_win_name,
                        "team_win_score": team_win_score,
                    }
                )

        return matchups

    def _matchups(self, start_week, end_week):
        matchup_data = []

        for week in range(start_week, end_week + 1):
            matchups = self.league.matchups(week)
            week_matchups = matchups["fantasy_content"]["league"][1]["scoreboard"]["0"]
            matchup = self._extract_matchup_info(week_matchups["matchups"])
            matchup_data.append(matchup)

        return matchup_data
        # matchup_data_json = json.dumps(matchup_data, indent=2)
        # with open("league_matchups.json", "w") as f:
        #     f.write(matchup_data_json)

    def _free_agents(self, position: str = "Util") -> Dict[str, Any]:
        """Implementation of abstract method - Get available free agents"""
        return self.league.free_agents(position)

        # free_agents_json = json.dumps(free_agents, indent=2)
        # with open("free_agents.json", "w") as f:
        #     f.write(free_agents_json)
        # return free_agents

    def _daily_roster(
        self, start_date: str, end_date: str, delay_seconds: float = 0.5
    ) -> Dict[str, Any]:
        """
        Implementation of abstract method - Get active players for ALL teams in a custom date range

        Args:
            start_date (str): Start date in 'YYYY-MM-DD' format
            end_date (str): End date in 'YYYY-MM-DD' format
            delay_seconds (float): Delay between API calls to avoid rate limiting

        Returns:
            dict: All teams data in format:
            {
                team_key: {
                    'team_name': str,
                    'daily_data': {date_str: [(player_name, position), ...]}
                }
            }
        """
        try:
            # Get all teams in the league
            teams = self.league.teams()

            # Calculate dates
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Store all data
            all_teams_data = {}

            # Loop through each team
            for team_key, team_info in teams.items():
                team_name = team_info.get("name", "Unknown Team")

                # Process each day for this team
                current_date = start_dt
                team_data = {}

                while current_date <= end_dt:
                    # Use the existing get_players_for_day function
                    active_players = self._get_players_for_day(
                        self.league, team_key, current_date
                    )
                    team_data[current_date.strftime("%Y-%m-%d")] = active_players

                    # Add delay to avoid getting rate-limited by the Yahoo API
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

                    current_date += timedelta(days=1)

                # Store team data
                all_teams_data[team_key] = {
                    "team_name": team_name,
                    "daily_data": team_data,
                }
                print(f"finished team: {team_key}")
            return self._export_daily_to_json_simple(all_teams_data)

        except Exception as e:
            return {}

    def _export_daily_to_json_simple(self, data, filename_prefix="daily_roster"):
        """
        Export fantasy data to simple JSON format:
        {
            "2024-03-18": {
                "Maccabi Secret": ["Jalen Suggs", "Kevin Durant", "Anthony Davis"],
                "Grimes for MVP": ["LeBron James", "Stephen Curry"]
            },
            "2024-03-19": {...}
        }
        """
        try:
            # Create timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.json"

            # Collect all dates and teams
            all_dates = set()
            team_info = {}

            # Process data to extract dates and team info
            for team_key, team_data in data.items():
                team_name = team_data.get("team_name", "Unknown")
                team_info[team_key] = team_name

                # Handle different data structures
                if "season_data" in team_data:
                    daily_data = team_data["season_data"]
                elif "daily_data" in team_data:
                    daily_data = team_data["daily_data"]
                else:
                    daily_data = team_data

                # Collect all dates
                all_dates.update(daily_data.keys())

            # Sort dates and teams
            sorted_dates = sorted(all_dates)
            sorted_teams = sorted(
                team_info.items(), key=lambda x: x[1]
            )  # Sort by team name

            # Build JSON structure
            json_data = {}

            # Process each date
            for date_str in sorted_dates:
                json_data[date_str] = {}

                # For each team
                for team_key, team_name in sorted_teams:
                    players_list = []

                    # Get team data
                    team_data = data.get(team_key, {})

                    # Handle different data structures
                    if "season_data" in team_data:
                        daily_data = team_data["season_data"]
                    elif "daily_data" in team_data:
                        daily_data = team_data["daily_data"]
                    else:
                        daily_data = team_data

                    # Get players for this date
                    players = daily_data.get(date_str, [])

                    if players:
                        for player_data in players:
                            if isinstance(player_data, tuple):
                                # Format: (player_name, position)
                                player_name, position = player_data
                                players_list.append(player_name)
                            elif isinstance(player_data, dict):
                                # Format: {'name': ..., 'position': ...}
                                player_name = player_data.get("name", "Unknown")
                                players_list.append(player_name)
                            else:
                                # Fallback
                                players_list.append(str(player_data))

                    json_data[date_str][team_name] = players_list

            # Write JSON file
            # with open(filename, 'w', encoding='utf-8') as jsonfile:
            #     json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)

            return json_data

        except Exception as e:
            return None

    def _get_players_for_day(self, league, team_key, date):
        """
        Get players for a specific team on a specific day
        Only include players who are NOT on the bench
        Returns list of tuples (player_name, position)
        """
        try:
            # Convert string date to datetime.date object if needed
            if isinstance(date, str):
                date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                date_obj = date

            # Get team and roster for that day
            team = league.to_team(team_key)
            roster = team.roster(day=date_obj)

            active_players = []

            for player in roster:
                player_name = player.get("name", "Unknown")
                selected_position = player.get("selected_position", "")

                # Filter out bench players - common bench symbols: 'BN', 'Bench', 'BE'
                if selected_position not in ["BN", "Bench", "BE", "IR", "IL", "IL+"]:
                    active_players.append((player_name, selected_position))

            return active_players

        except Exception as e:
            return []

    def _team_current_roster(self) -> Dict[str, Any]:
        """Implementation of abstract method - Get all teams current roster and export to team_roster.json"""
        try:
            # Get all teams in the league
            teams = self.league.teams()

            # Store all team rosters
            all_teams_rosters = {}

            # Loop through each team
            for team_key, team_info in teams.items():
                team_name = team_info.get("name", "Unknown Team")

                # Get current roster for this team
                team = self.league.to_team(team_key)
                roster = team.roster()

                # Store team roster
                all_teams_rosters[team_name] = roster

            # Export to JSON
            # team_roster_json = json.dumps(all_teams_rosters, indent=2)
            # with open("team_roster.json", "w") as f:
            #     f.write(team_roster_json)

            return all_teams_rosters

        except Exception as e:
            print(f"Error getting team rosters: {e}")
            return {}

    def sync_full_league(
        self,
        azure_blob_storage: AzureBlobStorage,
        start_week: int = 1,
        end_week: int = 20,
        days_back: int = 7,
    ) -> Dict[str, any]:
        """
        Sync all league data to Azure using robust upload with retries.
        Each blob is uploaded independently - one failure doesn't stop others.

        Args:
            azure_blob_storage: Azure Blob Storage instance for saving data
            start_week: Starting week for matchups (default: 1)
            end_week: Ending week for matchups (default: 20)
            days_back: Number of days back for daily roster (default: 7)

        Returns:
            Dict[str, bool]: Results mapping blob type to success status
                - True: Upload succeeded or was skipped (content unchanged)
                - False: Upload failed after retries

        Example:
            {
                'league_settings': True,
                'standings': True,
                'matchups': False,  # Failed
                'free_agents': True,
                'team_roster': True,
                'schedule': True,
                'daily_roster': True
            }
        """
        results = {}
        directory_name = self.league.league_id

        # 1. League settings
        try:
            league_settings = self._league_setting()
            success = azure_blob_storage.upload_json_with_retries(
                league_settings, f"{directory_name}/league_settings.json"
            )
            if success:
                results["league_settings"] = league_settings
        except Exception as e:
            logger.error(f"Error preparing league_settings: {e}")

        # 2. Standings
        try:
            standings = self._standings()
            success = azure_blob_storage.upload_json_with_retries(
                standings, f"{directory_name}/standings.json"
            )
            if success:
                results["standings"] = standings
        except Exception as e:
            logger.error(f"Error preparing standings: {e}")

        # 3. Matchups
        try:
            matchups = self._matchups(start_week, end_week)
            success = azure_blob_storage.upload_json_with_retries(
                matchups, f"{directory_name}/matchups.json"
            )
            if success:
                results["matchups"] = matchups
        except Exception as e:
            logger.error(f"Error preparing matchups: {e}")

        # 4. Free agents
        try:
            free_agents = self._free_agents()
            success = azure_blob_storage.upload_json_with_retries(
                free_agents, f"{directory_name}/free_agents.json"
            )
            if success:
                results["free_agents"] = free_agents
        except Exception as e:
            logger.error(f"Error preparing free_agents: {e}")

        # 5. Team current roster
        try:
            team_rosters = self._team_current_roster()
            success = azure_blob_storage.upload_json_with_retries(
                team_rosters, f"{directory_name}/team_roster.json"
            )
            if success:
                results["team_rosters"] = team_rosters
        except Exception as e:
            logger.error(f"Error preparing team_roster: {e}")

        # 6. Schedule
        try:
            schedule = self._schedule()
            success = azure_blob_storage.upload_json_with_retries(
                schedule, f"{directory_name}/schedule.json"
            )
            if success:
                results["schedule"] = schedule
        except Exception as e:
            logger.error(f"Error preparing schedule: {e}")

        # 7. Daily roster
        try:
            end_date = "2024-03-03"  # datetime.now().strftime('%Y-%m-%d')
            start_date = "2024-03-03"  # (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            daily_roster = self._daily_roster(start_date, end_date)
            success = azure_blob_storage.upload_json_with_retries(
                daily_roster, f"{directory_name}/daily_roster.json"
            )
            if success:
                results["daily_roster"] = daily_roster
        except Exception as e:
            logger.error(f"Error preparing daily_roster: {e}")

        # Log summary
        total_blobs = len(results)
        successful_blobs = sum(1 for v in results.values() if v)
        failed_blobs = total_blobs - successful_blobs

        logger.info(
            f"League {directory_name} sync complete: "
            f"{successful_blobs}/{total_blobs} succeeded, {failed_blobs} failed"
        )

        return results
