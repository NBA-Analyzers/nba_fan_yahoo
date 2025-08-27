from flask import Blueprint, request, session
from my_app.middleware.auth_decorators import require_google_auth
from my_app.services.yahoo_service import YahooService
from my_app.config.settings import DEBUG
from yahoo_oauth import OAuth2
from my_app.fantasy_platforms_integration.yahoo.sync_yahoo_league import YahooLeague
from my_app.azure.azure_blob_storage import AzureBlobStorage
from datetime import datetime
from my_app.supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
import yahoo_fantasy_api as yfa

yahoo_bp = Blueprint('yahoo', __name__, url_prefix='/yahoo')

@yahoo_bp.route('/select_league', methods=['POST'])
@require_google_auth
def select_league():
    """Handle league selection - Requires Google authentication first"""
    if DEBUG:
        sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
        yahoo_game = yfa.Game(sc, 'nba')
        league = yahoo_game.to_league('428.l.41083')
        yahoo_league = YahooLeague(league)
        results = yahoo_league.sync_full_league(azure_blob_storage=AzureBlobStorage(container_name="fantasy1"))
        return f"You synced: {results}" 

    try:
        league_id = request.form['league_id']
        user_guid = session.get('user')
        
        if not user_guid or 'token_store' not in session or user_guid not in session['token_store']:
            return "User not authenticated", 401
        
        # Use Yahoo service to sync league
        yahoo_service = YahooService(session['token_store'])
        result = yahoo_service.sync_league_data(league_id, user_guid)
        
        if 'error' in result:
            return f"<h2>Error</h2><p>{result['error']}</p><br><a href='/dashboard'>← Back to Dashboard</a>", 500
        
        return f"<h2>League Sync Complete!</h2><p>{result['db_message']}</p><p>Sync Results: {result['sync_results']}</p><br><a href='/dashboard'>← Back to Dashboard</a>"
        
    except Exception as e:
        print(f"❌ Error during league selection: {e}")
        return f"<h2>Error</h2><p>Failed to process league selection: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>", 500

@yahoo_bp.route('/my_leagues')
@require_google_auth
def my_leagues():
    """Get user's leagues from database - Requires Google authentication first"""
    try:
        user_guid = session.get('user')
        if not user_guid or 'token_store' not in session or user_guid not in session['token_store']:
            return "User not authenticated", 401
        
        # Use Yahoo service to get synced leagues
        yahoo_service = YahooService(session['token_store'])
        user_leagues = yahoo_service.get_user_synced_leagues(user_guid)
        
        if not user_leagues:
            return f"<h2>No Leagues Found</h2><p>You haven't synced any leagues yet.</p><br><a href='/dashboard'>← Back to Dashboard</a>"
        
        # Display leagues
        leagues_html = ""
        for league in user_leagues:
            leagues_html += f"""
            <div style="border: 1px solid #ccc; padding: 10px; margin: 10px 0; border-radius: 5px;">
                <h3>League ID: {league.get('league_id', 'Unknown')}</h3>
                <p><strong>Team:</strong> {league.get('team_name', 'Unknown Team')}</p>
                <p><strong>Added:</strong> {league.get('created_at', 'Unknown')}</p>
            </div>
            """
        
        return f"""
        <h2>Your Synced Leagues</h2>
        {leagues_html}
        <br>
        <a href='/dashboard'>← Back to Dashboard</a>
        """
        
    except Exception as e:
        print(f"❌ Error retrieving user leagues: {e}")
        return f"<h2>Error</h2><p>Failed to retrieve leagues: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>", 500

@yahoo_bp.route('/debug_league')
@require_google_auth
def debug_league():
    """Debug endpoint for league sync - Requires Google authentication first"""
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
        
        # For debug, use a placeholder yahoo_user_id
        yahoo_user_id = "debug_user_123"
        
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
        
        return f"<h2>Debug League Sync Complete!</h2><p>{db_message}</p><p>Sync Results: {results}</p><br><a href='/dashboard'>← Back to Dashboard</a>"
        
    except Exception as e:
        print(f"❌ Error during debug league sync: {e}")
        return f"<h2>Error</h2><p>Failed to process debug league sync: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>", 500
