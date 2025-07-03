import requests
import json
from yahoo_oauth import OAuth2
from typing import List, Dict
def get_latest_injury_news() -> List[Dict]:
    """Get latest NBA injury news from Yahoo Fantasy"""
    
    oauth = OAuth2(None, None, from_file='PythonProject2/oauth22.json')
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
    
    try:
        # Get games to find current season
        games_url = f"{base_url}/games;game_codes=nba"
        response = oauth.session.get(games_url, params={'format': 'json'})
        
        data = response.json()
        games_list = data['fantasy_content']['games']['0']['game']
        
        # Find current/recent season (not game_over)
        current_game = None
        for game in reversed(games_list):
            if int(game['game_key']) > 400:  # Recent seasons
                current_game = game
                break
        
        if not current_game:
            print("No current season found")
            return []
            
        game_key = current_game['game_key']
        print(f"Using season: {current_game['season']} (key: {game_key})")
        
        # Get players - no status filter
        players_url = f"{base_url}/game/{game_key}/players"
        response = oauth.session.get(players_url, params={'format': 'json', 'count': 100})
        
        if response.status_code != 200:
            print(f"Players API error: {response.status_code}")
            return []
            
        # Parse and filter for injured
        data = response.json()
        injured = []
        
        if 'fantasy_content' in data and 'game' in data['fantasy_content']:
            players_data = data['fantasy_content']['game'].get('players', {})
            
            for key in players_data:
                if key.isdigit():
                    player_info = players_data[key].get('player', {})
                    status = player_info.get('status', '')
                    
                    if status in ['IL', 'IL+', 'DTD', 'O', 'INJ']:
                        name = player_info.get('name', {})
                        injured.append({
                            'name': name.get('full', '') if isinstance(name, dict) else str(name),
                            'team': player_info.get('editorial_team_abbr', ''),
                            'status': status,
                            'injury_note': player_info.get('injury_note', '')
                        })
        
        return injured
        
    except Exception as e:
        print(f"Error: {e}")
        return []