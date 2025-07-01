
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv2, leaguegamefinder
from nba_api.stats.static import teams
import json
import time
from datetime import datetime, timedelta
import requests

def get_games_for_date_alternative(date_str):
    """
    Alternative method to get games using leaguegamefinder
    
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format
    
    Returns:
        list: List of game IDs and basic game info
    """
    try:
        print(f"Getting games for {date_str} using alternative method...")
        
        # Convert date format
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Use leaguegamefinder to get games for specific date
        gamefinder = leaguegamefinder.LeagueGameFinder(
            date_from_nullable=date_str,
            date_to_nullable=date_str
        )
        
        games_df = gamefinder.get_data_frames()[0]
        print(f"Found {len(games_df)} game entries")
        
        if games_df.empty:
            print(f"No games found for {date_str}")
            return []
        
        # Group by game_id since each game appears twice (once for each team)
        unique_games = {}
        
        for _, game in games_df.iterrows():
            game_id = game['GAME_ID']
            
            if game_id not in unique_games:
                unique_games[game_id] = {
                    'game_id': game_id,
                    'game_date': date_str,
                    'season_id': game.get('SEASON_ID', ''),
                    'game_date_est': game.get('GAME_DATE', date_str),
                    'teams': []
                }
            
            # Add team info
            team_info = {
                'team_id': game.get('TEAM_ID'),
                'team_abbreviation': game.get('TEAM_ABBREVIATION'),
                'team_name': game.get('TEAM_NAME'),
                'matchup': game.get('MATCHUP'),
                'wl': game.get('WL'),
                'pts': game.get('PTS')
            }
            unique_games[game_id]['teams'].append(team_info)
        
        games_list = list(unique_games.values())
        print(f"Unique games found: {len(games_list)}")
        
        return games_list
        
    except Exception as e:
        print(f"Error with alternative method: {e}")
        return []

def get_games_for_date_simple(date_str):
    """
    Simplified method to get games - just try to access known game IDs
    
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format
    
    Returns:
        list: List of game IDs and basic game info
    """
    try:
        print(f"Trying simple method for {date_str}...")
        
        # Convert date format for NBA API (MM/DD/YYYY)
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        nba_date_format = date_obj.strftime('%m/%d/%Y')
        
        print(f"NBA API date format: {nba_date_format}")
        
        # Try the scoreboard with minimal error handling
        try:
            scoreboard = scoreboardv2.ScoreboardV2(game_date=nba_date_format)
            print("Scoreboard object created successfully")
            
            # Try to get data frames
            try:
                data_frames = scoreboard.get_data_frames()
                print(f"Got {len(data_frames)} data frames")
                
                if len(data_frames) > 0:
                    games_data = data_frames[0]
                    print(f"Games data shape: {games_data.shape}")
                    print(f"Games data columns: {list(games_data.columns)}")
                    
                    if not games_data.empty:
                        games = []
                        for _, game in games_data.iterrows():
                            game_info = {
                                'game_id': str(game.get('GAME_ID', '')),
                                'game_date': date_str,
                                'home_team_id': game.get('HOME_TEAM_ID', 0),
                                'visitor_team_id': game.get('VISITOR_TEAM_ID', 0),
                            }
                            games.append(game_info)
                            print(f"Found game: {game_info['game_id']}")
                        
                        return games
                    else:
                        print("Games data frame is empty")
                        return []
                else:
                    print("No data frames returned")
                    return []
                    
            except Exception as df_error:
                print(f"Error getting data frames: {df_error}")
                return []
                
        except Exception as sb_error:
            print(f"Error creating scoreboard: {sb_error}")
            return []
        
    except Exception as e:
        print(f"Error in simple method: {e}")
        return []

def test_nba_api_connection():
    """
    Test if NBA API is working with a simple request
    """
    try:
        print("Testing NBA API connection...")
        
        # Try to get teams (this should always work)
        all_teams = teams.get_teams()
        print(f"✅ Successfully got {len(all_teams)} teams")
        
        # Try a simple scoreboard call for a known date with games
        test_date = "01/15/2024"  # A date that definitely had games
        print(f"Testing scoreboard for {test_date}...")
        
        scoreboard = scoreboardv2.ScoreboardV2(game_date=test_date)
        data_frames = scoreboard.get_data_frames()
        print(f"✅ Scoreboard test successful - {len(data_frames)} data frames")
        
        if len(data_frames) > 0:
            games_df = data_frames[0]
            print(f"✅ Games found: {len(games_df)}")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ NBA API test failed: {e}")
        return False

def get_games_for_date(date_str):
    """
    Get all NBA games for a specific date - tries multiple methods
    
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format
    
    Returns:
        list: List of game IDs and basic game info
    """
    print(f"🏀 Getting games for {date_str}...")
    
    # Method 1: Try the alternative leaguegamefinder approach
    print("Method 1: Using LeagueGameFinder...")
    games = get_games_for_date_alternative(date_str)
    if games:
        print(f"✅ Method 1 successful - found {len(games)} games")
        return games
    
    # Method 2: Try the simple scoreboard approach
    print("Method 2: Using simple ScoreboardV2...")
    games = get_games_for_date_simple(date_str)
    if games:
        print(f"✅ Method 2 successful - found {len(games)} games")
        return games
    
    # Method 3: Manual game ID generation (if we know the pattern)
    print("Method 3: No games found with either method")
    return []

def get_boxscore_for_game(game_id):
    """
    Get complete box score for a specific game
    
    Args:
        game_id (str): NBA game ID
    
    Returns:
        dict: Complete box score with all player stats
    """
    try:
        print(f"Getting box score for game {game_id}...")
        
        # Get traditional box score
        boxscore = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        
        # Get all data frames
        data_frames = boxscore.get_data_frames()
        print(f"Box score data frames: {len(data_frames)}")
        
        if len(data_frames) < 2:
            print(f"Insufficient data frames for game {game_id}")
            return None
        
        player_stats = data_frames[0]  # PlayerStats
        team_stats = data_frames[1]    # TeamStats
        
        print(f"Player stats shape: {player_stats.shape}")
        print(f"Team stats shape: {team_stats.shape}")
        
        # Process player stats
        players = []
        for _, player in player_stats.iterrows():
            # Handle None/NaN values safely
            def safe_get(value, default=0):
                if value is None or (hasattr(value, 'isna') and value.isna()):
                    return default
                return value
            
            player_data = {
                'player_id': safe_get(player.get('PLAYER_ID'), 0),
                'player_name': safe_get(player.get('PLAYER_NAME'), 'Unknown'),
                'team_id': safe_get(player.get('TEAM_ID'), 0),
                'team_abbreviation': safe_get(player.get('TEAM_ABBREVIATION'), ''),
                'team_city': safe_get(player.get('TEAM_CITY'), ''),
                'starter_bench': safe_get(player.get('START_POSITION'), ''),
                'minutes': safe_get(player.get('MIN'), '0:00'),
                'field_goals_made': safe_get(player.get('FGM'), 0),
                'field_goals_attempted': safe_get(player.get('FGA'), 0),
                'field_goal_percentage': safe_get(player.get('FG_PCT'), 0),
                'three_pointers_made': safe_get(player.get('FG3M'), 0),
                'three_pointers_attempted': safe_get(player.get('FG3A'), 0),
                'three_point_percentage': safe_get(player.get('FG3_PCT'), 0),
                'free_throws_made': safe_get(player.get('FTM'), 0),
                'free_throws_attempted': safe_get(player.get('FTA'), 0),
                'free_throw_percentage': safe_get(player.get('FT_PCT'), 0),
                'offensive_rebounds': safe_get(player.get('OREB'), 0),
                'defensive_rebounds': safe_get(player.get('DREB'), 0),
                'total_rebounds': safe_get(player.get('REB'), 0),
                'assists': safe_get(player.get('AST'), 0),
                'steals': safe_get(player.get('STL'), 0),
                'blocks': safe_get(player.get('BLK'), 0),
                'turnovers': safe_get(player.get('TO'), 0),
                'personal_fouls': safe_get(player.get('PF'), 0),
                'points': safe_get(player.get('PTS'), 0),
                'plus_minus': safe_get(player.get('PLUS_MINUS'), 0)
            }
            players.append(player_data)
        
        # Process team stats
        teams_data = []
        for _, team in team_stats.iterrows():
            team_data = {
                'team_id': safe_get(team.get('TEAM_ID'), 0),
                'team_name': safe_get(team.get('TEAM_NAME'), 'Unknown'),
                'team_abbreviation': safe_get(team.get('TEAM_ABBREVIATION'), ''),
                'team_city': safe_get(team.get('TEAM_CITY'), ''),
                'minutes': safe_get(team.get('MIN'), '240:00'),
                'field_goals_made': safe_get(team.get('FGM'), 0),
                'field_goals_attempted': safe_get(team.get('FGA'), 0),
                'field_goal_percentage': safe_get(team.get('FG_PCT'), 0),
                'three_pointers_made': safe_get(team.get('FG3M'), 0),
                'three_pointers_attempted': safe_get(team.get('FG3A'), 0),
                'three_point_percentage': safe_get(team.get('FG3_PCT'), 0),
                'free_throws_made': safe_get(team.get('FTM'), 0),
                'free_throws_attempted': safe_get(team.get('FTA'), 0),
                'free_throw_percentage': safe_get(team.get('FT_PCT'), 0),
                'offensive_rebounds': safe_get(team.get('OREB'), 0),
                'defensive_rebounds': safe_get(team.get('DREB'), 0),
                'total_rebounds': safe_get(team.get('REB'), 0),
                'assists': safe_get(team.get('AST'), 0),
                'steals': safe_get(team.get('STL'), 0),
                'blocks': safe_get(team.get('BLK'), 0),
                'turnovers': safe_get(team.get('TO'), 0),
                'personal_fouls': safe_get(team.get('PF'), 0),
                'points': safe_get(team.get('PTS'), 0),
                'plus_minus': safe_get(team.get('PLUS_MINUS'), 0)
            }
            teams_data.append(team_data)
        
        print(f"Processed {len(players)} players and {len(teams_data)} teams")
        
        return {
            'players': players,
            'teams': teams_data
        }
        
    except Exception as e:
        print(f"Error getting box score for game {game_id}: {e}")
        print(f"Error type: {type(e)}")
        return None

def get_all_boxscores_for_date(date_str):
    """
    Get complete box scores for all NBA games on a specific date
    
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format
    
    Returns:
        dict: Complete daily box scores for all games
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Get all games for the date
        games = get_games_for_date(date_str)
        
        if not games:
            return {
                'date': date_str,
                'day_of_week': date_obj.strftime('%A'),
                'games_count': 0,
                'games': [],
                'all_players': {},
                'summary': {
                    'total_games': 0,
                    'total_players': 0,
                    'total_teams': 0
                }
            }
        
        daily_data = {
            'date': date_str,
            'day_of_week': date_obj.strftime('%A'),
            'games_count': len(games),
            'games': [],
            'all_players': {},
            'summary': {
                'total_games': len(games),
                'total_players': 0,
                'total_teams': 0
            }
        }
        
        # Process each game
        for game_info in games:
            print(f"Processing game {game_info['game_id']}...")
            
            # Get box score for this game
            boxscore = get_boxscore_for_game(game_info['game_id'])
            
            if boxscore:
                # Combine game info with box score
                complete_game = {
                    **game_info,
                    'players': boxscore['players'],
                    'teams': boxscore['teams']
                }
                
                daily_data['games'].append(complete_game)
                
                # Add players to global players dict
                for player in boxscore['players']:
                    player_key = f"{player['player_name']}_{player['team_abbreviation']}"
                    daily_data['all_players'][player_key] = {
                        'game_id': game_info['game_id'],
                        **player
                    }
                
                # Update summary
                daily_data['summary']['total_players'] += len(boxscore['players'])
                daily_data['summary']['total_teams'] += len(boxscore['teams'])
            
            # Rate limiting - NBA API has limits
            time.sleep(0.6)  # Wait 600ms between requests
        
        return daily_data
        
    except Exception as e:
        print(f"Error getting daily box scores for {date_str}: {e}")
        return None

def export_daily_boxscores_to_json(daily_data, filename_prefix="nba_boxscores"):
    """
    Export daily box scores to JSON file
    
    Args:
        daily_data: Dictionary from get_all_boxscores_for_date
        filename_prefix: Prefix for the filename
    
    Returns:
        str: Filename of exported file
    """
    try:
        if not daily_data:
            return None
        
        date_str = daily_data.get('date', 'unknown_date')
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{filename_prefix}_{date_str}_{timestamp}.json"
        
        # Write JSON file
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(daily_data, jsonfile, indent=2, ensure_ascii=False)
        
        return filename
        
    except Exception as e:
        print(f"Error exporting daily box scores: {e}")
        return None

def collect_and_export_nba_boxscores(date_str, filename_prefix="nba_boxscores"):
    """
    One-function solution: Get all NBA box scores for a date and export to JSON
    
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format
        filename_prefix: Prefix for the JSON filename
    
    Returns:
        str: Filename of exported JSON file
    """
    print(f"🏀 Collecting NBA box scores for {date_str}...")
    
    # Get all box scores for the date
    daily_data = get_all_boxscores_for_date(date_str)
    
    if daily_data:
        # Export to JSON
        filename = export_daily_boxscores_to_json(daily_data, filename_prefix)
        
        if filename:
            print(f"✅ NBA box scores exported to: {filename}")
            print(f"📊 Summary:")
            print(f"   Games: {daily_data['summary']['total_games']}")
            print(f"   Players: {daily_data['summary']['total_players']}")
            print(f"   Teams: {daily_data['summary']['total_teams']}")
            return filename
    
    print(f"❌ Failed to collect box scores for {date_str}")
    return None

def collect_multiple_dates(start_date, end_date, filename_prefix="nba_boxscores"):
    """
    Collect NBA box scores for multiple dates
    
    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        filename_prefix: Prefix for JSON filenames
    
    Returns:
        list: List of created filenames
    """
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    current_date = start_dt
    created_files = []
    
    while current_date <= end_dt:
        date_str = current_date.strftime('%Y-%m-%d')
        
        print(f"\n--- Processing {date_str} ---")
        filename = collect_and_export_nba_boxscores(date_str, filename_prefix)
        
        if filename:
            created_files.append(filename)
        
        # Move to next day
        current_date += timedelta(days=1)
        
        # Rate limiting between days
        time.sleep(1)
    
    print(f"\n🎉 Completed! Created {len(created_files)} files:")
    for file in created_files:
        print(f"   📁 {file}")
    
    return created_files
