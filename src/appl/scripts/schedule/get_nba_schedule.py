from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.endpoints._base import Endpoint
from nba_api.stats.static import teams
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import time

# Define a custom class that inherits from ScoreboardV2 to fix the KeyError
class CustomScoreboardV2(scoreboardv2.ScoreboardV2):
    def load_response(self):
        # This method is copied/adapted from the original library to handle missing keys
        data_sets = self.nba_response.get_data_sets()
        self.game_header = Endpoint.DataSet(data=data_sets['GameHeader'])
        self.line_score = Endpoint.DataSet(data=data_sets['LineScore'])
        self.series_standings = Endpoint.DataSet(data=data_sets['SeriesStandings'])
        self.last_meeting = Endpoint.DataSet(data=data_sets['LastMeeting'])
        self.east_conf_standings_by_day = Endpoint.DataSet(data=data_sets['EastConfStandingsByDay'])
        self.west_conf_standings_by_day = Endpoint.DataSet(data=data_sets['WestConfStandingsByDay'])
        self.available = Endpoint.DataSet(data=data_sets['Available'])
        self.team_leaders = Endpoint.DataSet(data=data_sets['TeamLeaders'])
        self.ticket_links = Endpoint.DataSet(data=data_sets['TicketLinks'])
        
        # The original code fails here for future games because 'WinProbability' is missing
        if 'WinProbability' in data_sets:
            self.win_probability = Endpoint.DataSet(data=data_sets['WinProbability'])
        else:
            self.win_probability = None

def get_future_schedule():
    # Configuration
    start_date = datetime.now() + timedelta(days=1)
    end_date = datetime(2026, 4, 13) # Approx end of regular season
    
    print(f"Fetching schedule from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    
    # Pre-fetch team data for mapping
    nba_teams = teams.get_teams()
    team_map = {team['id']: team['full_name'] for team in nba_teams}
    
    schedule_by_date = {}
    current_date = start_date
    total_games = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"Fetching games for {date_str}...", end="\r")
        
        try:
            # Use the custom class
            board = CustomScoreboardV2(game_date=date_str)
            games = board.game_header.get_data_frame()
            
            if not games.empty:
                games_dict = games.to_dict('records')
                daily_games = []
                seen_game_ids = set()
                
                for game in games_dict:
                    game_id = game.get('GAME_ID')
                    if game_id in seen_game_ids:
                        continue
                    seen_game_ids.add(game_id)
                    
                    home_id = game.get('HOME_TEAM_ID')
                    visitor_id = game.get('VISITOR_TEAM_ID')
                    
                    clean_game = {
                        'home_team': team_map.get(home_id, f"Unknown ({home_id})"),
                        'away_team': team_map.get(visitor_id, f"Unknown ({visitor_id})"),
                        'game_id': game_id
                    }
                    daily_games.append(clean_game)
                
                if daily_games:
                    schedule_by_date[date_str] = daily_games
                    total_games += len(daily_games)
                
        except Exception as e:
            print(f"\nError fetching {date_str}: {e}")
            
        # Respect rate limits
        time.sleep(0.5) 
        current_date += timedelta(days=1)

    print(f"\nTotal games found: {total_games}")
    
    # Save to JSON
    output_dir = "nba_fan_yahoo/src/appl/data/schedule"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "NBA_schedule.json")
    
    with open(output_file, 'w') as f:
        json.dump(schedule_by_date, f, indent=4)
        
    print(f"Schedule saved to {output_file}")

if __name__ == "__main__":
    get_future_schedule()