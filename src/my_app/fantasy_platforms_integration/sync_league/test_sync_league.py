from yahoo_fantasy_api.league import yfa
from yahoo_oauth import OAuth2


sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
yahoo_game = yfa.Game(sc, 'nba')
lg = yahoo_game.to_league('428.l.41083')
all_players = lg.taken_players()
            
# Filter for injured NBA players
injured_nba_players = []

for player in all_players:
    status = player.get('status', '').strip()
    
    # NBA injury statuses
    if status and status not in ['', 'Healthy', 'Active']:
        injured_nba_players.append({
            'player_id': player.get('player_id'),
            'name': player.get('name'),
            'injury_status': player.get('status', 'Healthy'),
        
        })


print(f"📊 Found {len(injured_nba_players)} injured NBA players")
print( injured_nba_players)