from flask import Blueprint, jsonify
from ..middleware.auth_decorators import require_google_auth
from ..config.settings import DEBUG
from yahoo_oauth import OAuth2
from my_app.integrations.yahoo.sync_yahoo_league import YahooLeague
from ..supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
from datetime import datetime
import yahoo_fantasy_api as yfa

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/sync_league')
@require_google_auth
def sync_league():
    """Direct sync endpoint - Requires Google authentication first"""
    try:
        sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
        yahoo_game = yfa.Game(sc, 'nba')
        league = yahoo_game.to_league('428.l.41083')
        
        # Get league information for database insertion
        league_settings = league.settings()
        league_name = league_settings.get('name', 'Unknown League')
        
        # Get user's team information
        teams = league.teams()
        user_team_name = None
        
        # Find the user's team (assuming first team is the user's)
        if teams:
            first_team_key = list(teams.keys())[0]
            user_team_name = teams[first_team_key].get('name', 'Unknown Team')
        
        # For direct sync, use a placeholder yahoo_user_id
        yahoo_user_id = "direct_sync_user_123"
        
        # Insert into yahoo_league table
        yahoo_league_repo = YahooLeagueRepository()
        league_data = {
            'yahoo_user_id': yahoo_user_id,
            'league_id': '428.l.41083',
            'team_name': user_team_name or 'Unknown Team',
            'created_at': datetime.now().isoformat()
        }
        
        # Check if league already exists for this user
        existing_league = yahoo_league_repo.get_by_league_id('428.l.41083')
        if existing_league:
            # Update existing record
            yahoo_league_repo.update_by_league_id('428.l.41083', league_data)
            db_message = "League updated in database"
        else:
            # Create new record
            yahoo_league_repo.create(league_data)
            db_message = "League added to database"
        
        # Sync league data
        yahoo_league = YahooLeague(league)
        results = yahoo_league.sync_full_league()
        
        return jsonify({
            "message": "League sync completed",
            "db_message": db_message,
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
