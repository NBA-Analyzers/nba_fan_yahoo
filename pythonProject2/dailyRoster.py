from datetime import datetime,timedelta
import csv
import os
import time
import json

def print_players_for_day(league, team_key, date):
    """
    Print players for a specific team on a specific day
    Only include players who are NOT on the bench
    """
    try:
        # Convert string date to datetime.date object if needed
        if isinstance(date, str):
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        else:
            date_obj = date
        
        # Get team and roster for that day
        team = league.to_team(team_key)
        roster = team.roster(day=date_obj)
        
        print(f"Active players for {team_key} on {date_obj}:")
        
        active_players = []
        bench_players = []
        
        for player in roster:
            player_name = player.get('name', 'Unknown')
            selected_position = player.get('selected_position', '')
            
            # Filter out bench players - common bench symbols: 'BN', 'Bench', 'BE'
            if selected_position in ['BN', 'Bench', 'BE', 'IR','IL','IL+']:
                bench_players.append(player_name)
            else:
                active_players.append((player_name, selected_position))
                print(f"  - {player_name} ({selected_position})")
        
        print(f"Total active players: {len(active_players)}")
        print(f"Bench players: {len(bench_players)}")
        
        return active_players
        
    except Exception as e:
        print(f"Error: {e}")
        return []


def print_players_entire_season(league, team_key):
    """
    Print active players for every day from league start to end of regular season
    Uses the league's start_date and end_date settings
    
    Args:
        league: Yahoo Fantasy League object
        team_key (str): Team key
    """
    try:
        # Get league settings to find start and end dates
        settings = league.settings()
        
        start_date_str = settings.get('start_date')  # e.g., '2023-10-24'
        end_date_str = settings.get('end_date')      # e.g., '2024-03-24'
        
        print(f"=== Entire Season: {start_date_str} to {end_date_str} ===")
        print(f"League: {settings.get('name', 'Unknown League')}")
        print(f"Season: {settings.get('season', 'Unknown')}\n")
        
        # Convert to date objects
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        current_date = start_date
        all_season_data = {}
        day_count = 0
        
        while current_date <= end_date:
            day_count += 1
            print(f"=== Day {day_count}: {current_date} ===")
            
            # Use the existing print_players_for_day function
            active_players = print_players_for_day(league, team_key, current_date)
            
            # Store the data
            all_season_data[current_date.strftime('%Y-%m-%d')] = active_players
            
            print()  # Empty line between days
            current_date += timedelta(days=1)
        
        # Final summary
        print(f"=== Season Complete ===")
        print(f"Total days processed: {day_count}")
        print(f"Days with active players: {len([d for d in all_season_data.values() if d])}")
        
        return all_season_data
        
    except Exception as e:
        print(f"Error getting season data: {e}")
        return {}

def print_all_teams_custom_range(league, start_date, end_date):
    """
    Print active players for ALL teams in a custom date range
    Uses the existing functions for each team
    
    Args:
        league: Yahoo Fantasy League object
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
    """
    try:
        # Get all teams in the league
        teams = league.teams()
        team_count = len(teams)
        
        # Calculate days and estimated calls
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        total_days = (end_dt - start_dt).days + 1
        estimated_calls = team_count * total_days
        
        print(f"=== ALL TEAMS - Custom Range ===")
        print(f"Date Range: {start_date} to {end_date}")
        print(f"Teams: {team_count}")
        print(f"Total Days: {total_days}")
        print(f"Estimated API Calls: {estimated_calls}\n")
        
        # Store all data
        all_teams_data = {}
        team_number = 0
        
        # Loop through each team
        for team_key, team_info in teams.items():
            team_number += 1
            team_name = team_info.get('name', 'Unknown Team')
            
            print(f"" + "-"*60)
            print(f"TEAM {team_number}/{team_count}: {team_name}")
            print(f"" + "-"*60)
            
            # Process each day for this team
            current_date = start_dt
            team_data = {}
            
            while current_date <= end_dt:
                print(f"\n--- {current_date} ---")
                
                # Use the existing print_players_for_day function
                active_players = print_players_for_day(league, team_key, current_date)
                team_data[current_date.strftime('%Y-%m-%d')] = active_players
                
                # --- IMPORTANT ---
                # Add a delay to avoid getting rate-limited by the Yahoo API
                time.sleep(1) 
                
                current_date += timedelta(days=1)
            
            # Store team data
            all_teams_data[team_key] = {
                'team_name': team_name,
                'daily_data': team_data
            }
            
            # Team summary
            days_with_players = len([d for d in team_data.values() if d])
            total_active = sum(len(players) for players in team_data.values())
            avg_active = total_active / len(team_data) if team_data else 0
            
            print(f"\n✅ {team_name} Summary:")
            print(f"   Days with active players: {days_with_players}/{len(team_data)}")
            print(f"   Average active players: {avg_active:.1f}")
            print(f"" + "-"*60 + "\n")
        
        # Final summary
        print(f"" + "="*60)
        print(f"🎉 ALL TEAMS RANGE ANALYSIS COMPLETE! 🎉")
        print(f"" + "="*60)
        
        print(f"\n=== FINAL SUMMARY ===")
        for team_key, team_data in all_teams_data.items():
            team_name = team_data['team_name']
            daily_data = team_data['daily_data']
            
            days_with_players = len([d for d in daily_data.values() if d])
            total_active = sum(len(players) for players in daily_data.values())
            avg_active = total_active / len(daily_data) if daily_data else 0
            
            print(f"  {team_name}: {avg_active:.1f} avg active players")
        
        return all_teams_data
        
    except Exception as e:
        print(f"Error in print_all_teams_custom_range: {e}")
        return {}


def export_to_csv_pivot(data, filename_prefix="yahoo_fantasy_pivot"):
    """
    Export fantasy data to a pivot-style CSV:
    - Rows: Dates
    - Columns: Team Names  
    - Cells: List of active players (comma-separated)
    
    Args:
        data: Dictionary containing team and player data
        filename_prefix: Prefix for the CSV filename
    """
    try:
        # Create timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.csv"
        
        # Collect all dates and teams
        all_dates = set()
        team_info = {}
        
        # Process data to extract dates and team info
        for team_key, team_data in data.items():
            team_name = team_data.get('team_name', 'Unknown')
            team_info[team_key] = team_name
            
            # Handle different data structures
            if 'season_data' in team_data:
                daily_data = team_data['season_data']
            elif 'daily_data' in team_data:
                daily_data = team_data['daily_data']
            else:
                daily_data = team_data
            
            # Collect all dates
            all_dates.update(daily_data.keys())
        
        # Sort dates
        sorted_dates = sorted(all_dates)
        sorted_teams = sorted(team_info.items(), key=lambda x: x[1])  # Sort by team name
        
        print(f"Creating pivot CSV with:")
        print(f"  📅 Dates (rows): {len(sorted_dates)}")
        print(f"  🏀 Teams (columns): {len(sorted_teams)}")
        
        # Create CSV
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Create header: Date + Team Names
            fieldnames = ['date'] + [team_name for team_key, team_name in sorted_teams]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Process each date (row)
            for date_str in sorted_dates:
                row_data = {'date': date_str}
                
                # For each team (column)
                for team_key, team_name in sorted_teams:
                    players_list = []
                    
                    # Get team data
                    team_data = data.get(team_key, {})
                    
                    # Handle different data structures
                    if 'season_data' in team_data:
                        daily_data = team_data['season_data']
                    elif 'daily_data' in team_data:
                        daily_data = team_data['daily_data']
                    else:
                        daily_data = team_data
                    
                    # Get players for this date
                    players = daily_data.get(date_str, [])
                    
                    if players:
                        for player_data in players:
                            if isinstance(player_data, tuple):
                                # Format: (player_name, position)
                                player_name, position = player_data
                                players_list.append(f"{player_name} ({position})")
                            elif isinstance(player_data, dict):
                                # Format: {'name': ..., 'position': ...}
                                player_name = player_data.get('name', 'Unknown')
                                position = player_data.get('position', '')
                                if position:
                                    players_list.append(f"{player_name} ({position})")
                                else:
                                    players_list.append(player_name)
                            else:
                                # Fallback
                                players_list.append(str(player_data))
                    
                    # Join players with semicolon for better CSV compatibility
                    row_data[team_name] = '; '.join(players_list) if players_list else ''
                
                writer.writerow(row_data)
        
        print(f"✅ Pivot CSV exported to: {filename}")
        print(f"📊 Format: {len(sorted_dates)} rows × {len(sorted_teams)+1} columns")
        
        return filename
        
    except Exception as e:
        print(f"❌ Error exporting pivot CSV: {e}")
        return None


def export_to_json_pivot(data, filename_prefix="yahoo_fantasy_pivot"):
    """
    Export fantasy data to JSON in pivot format:
    {
        "2024-03-18": {
            "Maccabi Secret": [
                {"name": "Jalen Suggs", "position": "PG"},
                {"name": "Kevin Durant", "position": "SF"}
            ],
            "Grimes for MVP": [...]
        },
        "2024-03-19": {...}
    }
    
    Args:
        data: Dictionary containing team and player data
        filename_prefix: Prefix for the JSON filename
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
            team_name = team_data.get('team_name', 'Unknown')
            team_info[team_key] = team_name
            
            # Handle different data structures
            if 'season_data' in team_data:
                daily_data = team_data['season_data']
            elif 'daily_data' in team_data:
                daily_data = team_data['daily_data']
            else:
                daily_data = team_data
            
            # Collect all dates
            all_dates.update(daily_data.keys())
        
        # Sort dates and teams
        sorted_dates = sorted(all_dates)
        sorted_teams = sorted(team_info.items(), key=lambda x: x[1])  # Sort by team name
        
        print(f"Creating pivot JSON with:")
        print(f"  📅 Dates: {len(sorted_dates)}")
        print(f"  🏀 Teams: {len(sorted_teams)}")
        
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
                if 'season_data' in team_data:
                    daily_data = team_data['season_data']
                elif 'daily_data' in team_data:
                    daily_data = team_data['daily_data']
                else:
                    daily_data = team_data
                
                # Get players for this date
                players = daily_data.get(date_str, [])
                
                if players:
                    for player_data in players:
                        if isinstance(player_data, tuple):
                            # Format: (player_name, position)
                            player_name, position = player_data
                            players_list.append({
                                "name": player_name,
                                "position": position
                            })
                        elif isinstance(player_data, dict):
                            # Format: {'name': ..., 'position': ...}
                            player_name = player_data.get('name', 'Unknown')
                            position = player_data.get('position', '')
                            players_list.append({
                                "name": player_name,
                                "position": position
                            })
                        else:
                            # Fallback
                            players_list.append({
                                "name": str(player_data),
                                "position": ""
                            })
                
                json_data[date_str][team_name] = players_list
        
        # Write JSON file
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)
        
        print(f"✅ Pivot JSON exported to: {filename}")
        print(f"📊 Structure: {len(sorted_dates)} dates × {len(sorted_teams)} teams")
        
        return filename
        
    except Exception as e:
        print(f"❌ Error exporting pivot JSON: {e}")
        return None