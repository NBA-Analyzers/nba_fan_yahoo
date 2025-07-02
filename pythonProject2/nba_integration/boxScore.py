from nba_api.stats.endpoints import leaguegamefinder, boxscoretraditionalv2, scoreboardv2
from nba_api.stats.static import teams
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

def get_box_score(game_id: str, game_date: str) -> List[Dict]:
    """Get flattened player stats for a specific game"""
    try:
        boxscore = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        player_stats = boxscore.get_data_frames()[0]
        
        # Filter to only desired columns
        desired_columns = [
            "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "MIN", "FGM", "FGA", "FG_PCT",
            "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB", 
            "REB", "AST", "STL", "BLK", "TO", "PTS"
        ]
        
        filtered_stats = player_stats[desired_columns]
        
        # Get unique teams to determine opponent
        teams_in_game = filtered_stats['TEAM_ABBREVIATION'].unique()
        
        flattened_players = []
        for _, player in filtered_stats.iterrows():
            # Skip players who didn't play (null minutes)
            if pd.isna(player['MIN']) or player['MIN'] is None:
                continue
                
            # Determine opponent
            player_team = player['TEAM_ABBREVIATION']
            opponent = [team for team in teams_in_game if team != player_team][0]
            
            player_record = {
                "game_id": game_id,
                "game_date": game_date,
                "player_name": player['PLAYER_NAME'],
                "team": player_team,
                "opponent": opponent,
                "MIN": player['MIN'],
                "FGM": int(player['FGM']) if not pd.isna(player['FGM']) else 0,
                "FGA": int(player['FGA']) if not pd.isna(player['FGA']) else 0,
                "FG_PCT": round(player['FG_PCT'], 3) if not pd.isna(player['FG_PCT']) else 0.0,
                "FG3M": int(player['FG3M']) if not pd.isna(player['FG3M']) else 0,
                "FG3A": int(player['FG3A']) if not pd.isna(player['FG3A']) else 0,
                "FG3_PCT": round(player['FG3_PCT'], 3) if not pd.isna(player['FG3_PCT']) else 0.0,
                "FTM": int(player['FTM']) if not pd.isna(player['FTM']) else 0,
                "FTA": int(player['FTA']) if not pd.isna(player['FTA']) else 0,
                "FT_PCT": round(player['FT_PCT'], 3) if not pd.isna(player['FT_PCT']) else 0.0,
                "OREB": int(player['OREB']) if not pd.isna(player['OREB']) else 0,
                "DREB": int(player['DREB']) if not pd.isna(player['DREB']) else 0,
                "REB": int(player['REB']) if not pd.isna(player['REB']) else 0,
                "AST": int(player['AST']) if not pd.isna(player['AST']) else 0,
                "STL": int(player['STL']) if not pd.isna(player['STL']) else 0,
                "BLK": int(player['BLK']) if not pd.isna(player['BLK']) else 0,
                "TO": int(player['TO']) if not pd.isna(player['TO']) else 0,
                "PTS": int(player['PTS']) if not pd.isna(player['PTS']) else 0
            }
            flattened_players.append(player_record)
            
        return flattened_players
        
    except Exception as e:
        print(f"Error fetching box score for game {game_id}: {e}")
        return []

def get_season_games(season='2024-25'):
    """Get all games for the season"""
    print(f"Fetching all games for {season} season...")
    
    game_finder = leaguegamefinder.LeagueGameFinder(
        season_nullable=season,
        league_id_nullable='00'
    )
    
    games_df = game_finder.get_data_frames()[0]
    games_df = games_df.drop_duplicates(subset=['GAME_ID'])
    
    print(f"Found {len(games_df)} games")
    return games_df

def get_games_by_date_range(start_date: str, end_date: str, season='2024-25'):
    """Get flattened player stats for games between specific dates"""
    print(f"Fetching games from {start_date} to {end_date}...")
    
    games_df = get_season_games(season)
    
    # Filter by date range
    games_df['GAME_DATE'] = pd.to_datetime(games_df['GAME_DATE'])
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    
    filtered_games = games_df[
        (games_df['GAME_DATE'] >= start_dt) & 
        (games_df['GAME_DATE'] <= end_dt)
    ]
    
    print(f"Found {len(filtered_games)} games in date range")
    
    # Get flattened player stats
    return get_all_box_scores(filtered_games)

def get_all_box_scores(games_df: pd.DataFrame) -> List[Dict]:
    """Get flattened player stats for all games"""
    all_players = []
    total_games = len(games_df)
    
    for i, (_, game) in enumerate(games_df.iterrows()):
        game_id = game['GAME_ID']
        game_date = game['GAME_DATE'].strftime('%Y-%m-%d')
        
        print(f"Fetching box score {i+1}/{total_games} - Game ID: {game_id}")
        
        players = get_box_score(game_id, game_date)
        all_players.extend(players)
        
        time.sleep(0.6)  # Rate limiting
    
    return all_players

def get_sample_games(days_back: int = 7) -> List[Dict]:
    """Get flattened player stats from recent days"""
    end_date = datetime.now()
    all_players = []
    
    for i in range(days_back):
        date = end_date - timedelta(days=i)
        date_str = date.strftime('%m/%d/%Y')
        
        try:
            scoreboard = scoreboardv2.ScoreboardV2(game_date=date_str)
            games_df = scoreboard.get_data_frames()[0]
            
            if not games_df.empty:
                for _, game in games_df.iterrows():
                    game_id = game['GAME_ID']
                    game_date = date.strftime('%Y-%m-%d')
                    players = get_box_score(game_id, game_date)
                    all_players.extend(players)
                    time.sleep(0.6)
                    
                print(f"Found {len(games_df)} games on {date_str}")
                
        except Exception as e:
            print(f"No games found for {date_str}")
        
    return all_players

def save_to_json(data: List[Dict], filename: str):
    """Save flattened data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Data saved to {filename}")

def save_to_csv(data: List[Dict], filename: str):
    """Save flattened data to CSV file"""
    if data:
        pd.DataFrame(data).to_csv(filename, index=False)
        print(f"Data saved to {filename}")
