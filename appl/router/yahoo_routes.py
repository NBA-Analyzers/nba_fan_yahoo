from datetime import datetime
from urllib.parse import quote

import yahoo_fantasy_api as yfa
from service.openai_file_manager import OpenaiFileManager
from config.app_config import DEBUG
from fantasy_integrations.yahoo.sync_league.sync_yahoo_league import YahooLeague
from fantasy_integrations.yahoo.sync_league.yahoo_service import (
    YahooService,
    get_yahoo_sdk,
)
from flask import Blueprint, request, session
from middleware.auth_decorators import require_google_auth
from repository.azure.azure_blob_storage import AzureBlobStorage
from repository.supaBase.repositories.yahoo_league_repository import (
    YahooLeagueRepository,
)
from yahoo_oauth import OAuth2


class YahooRouter:
    
    def __init__(self, openai_file_manager: OpenaiFileManager):
        self.openai_file_manager = openai_file_manager
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        
        yahoo_bp = Blueprint("yahoo", __name__, url_prefix="/yahoo")

        @yahoo_bp.route("/select_league", methods=["POST"])
        @require_google_auth
        def select_league():
            """Handle league selection - Requires Google authentication first"""
            if DEBUG:
                sc = OAuth2(
                    None,
                    None,
                    from_file="src/my_app/fantasy_platforms_integration/yahoo/oauth22.json",
                )
                yahoo_game = yfa.Game(sc, "nba")
                league = yahoo_game.to_league("428.l.41083")
                yahoo_league = YahooLeague(league)
                results = yahoo_league.sync_full_league(
                    azure_blob_storage=AzureBlobStorage(container_name="fantasy1")
                )
                return f"You synced: {results}"

            try:
                league_id = request.form["league_id"]
                user_guid = session.get("user")

                if (
                    not user_guid
                    or "token_store" not in session
                    or user_guid not in session["token_store"]
                ):
                    return "User not authenticated", 401

                # Use Yahoo service to sync league
                yahoo_service = YahooService(session["token_store"], self.openai_file_manager)
                result = yahoo_service.sync_league_data(league_id, user_guid)

                if "error" in result:
                    return (
                        f"<h2>Error</h2><p>{result['error']}</p><br><a href='/dashboard'>← Back to Dashboard</a>",
                        500,
                    )

                # Get league name for the redirect
                try:
                    yahoo_game = get_yahoo_sdk(session["token_store"], {"user": user_guid})
                    league = yahoo_game.to_league(league_id)
                    league_settings = league.settings()
                    league_name = league_settings.get("name", "Unknown League")
                except Exception:
                    league_name = "Unknown League"

                # URL encode the league name to handle special characters

                encoded_league_name = quote(league_name)

                # Redirect to league-specific AI chat page after successful league sync
                return f"""
                <h2>🎉 League Connected Successfully!</h2>
                <p>{result.get("db_message", "League sync completed")}</p>
                <p><strong>League:</strong> {league_name}</p>
                <p>Your league data has been synced and you're ready to use the AI Assistant!</p>
                <br>
                <a href='/ai-chat/{league_id}' style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-size: 18px;">🚀 Go to AI Chat for {league_name}</a>
                <br><br>
                <a href='/dashboard'>← Back to Dashboard</a>
                """

            except Exception as e:
                print(f"❌ Error during league selection: {e.message}")
                return (
                    f"<h2>Error</h2><p>Failed to process league selection: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>",
                    500,
                )


        @yahoo_bp.route("/my_leagues")
        @require_google_auth
        def my_leagues():
            """Get user's leagues from database - Requires Google authentication first"""
            try:
                user_guid = session.get("user")
                if (
                    not user_guid
                    or "token_store" not in session
                    or user_guid not in session["token_store"]
                ):
                    return "User not authenticated", 401

                # Use Yahoo service to get synced leagues
                yahoo_service = YahooService(session["token_store"], self.openai_file_manager)
                user_leagues = yahoo_service.get_user_synced_leagues(user_guid)

                if not user_leagues:
                    return f"<h2>No Leagues Found</h2><p>You haven't synced any leagues yet.</p><br><a href='/dashboard'>← Back to Dashboard</a>"

                # Display leagues
                leagues_html = ""
                for league in user_leagues:
                    leagues_html += f"""
                    <div style="border: 1px solid #ccc; padding: 15px; margin: 15px 0; border-radius: 8px; background: white;">
                        <h3>League ID: {league.get("league_id", "Unknown")}</h3>
                        <p><strong>Team:</strong> {league.get("team_name", "Unknown Team")}</p>
                        <p><strong>Added:</strong> {league.get("created_at", "Unknown")}</p>
                        <div style="margin-top: 15px;">
                            <a href="/ai-chat/{league.get("league_id", "unknown")}" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🚀 AI Chat</a>
                            <a href="/dashboard" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Dashboard</a>
                        </div>
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
                return (
                    f"<h2>Error</h2><p>Failed to retrieve leagues: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>",
                    500,
                )


        @yahoo_bp.route("/debug_league")
        @require_google_auth
        def debug_league():
            """Debug endpoint for league sync - Requires Google authentication first"""
            try:
                sc = OAuth2(
                    None,
                    None,
                    from_file="src/my_app/fantasy_platforms_integration/yahoo/oauth22.json",
                )
                yahoo_game = yfa.Game(sc, "nba")
                league = yahoo_game.to_league("428.l.41083")

                # Get league information for database insertion
                league_settings = league.settings()
                league_name = league_settings.get("name", "Unknown League")

                # Get user's team information
                teams = league.teams()
                user_team_name = None
                user_team_id = None

                # Find the user's team (assuming first team is the user's)
                if teams:
                    first_team_key = list(teams.keys())[0]
                    user_team_name = teams[first_team_key].get("name", "Unknown Team")
                    user_team_id = first_team_key

                # For debug, use a placeholder yahoo_user_id
                yahoo_user_id = "debug_user_123"

                # Insert into yahoo_league table
                yahoo_league_repo = YahooLeagueRepository()
                league_data = {
                    "yahoo_user_id": yahoo_user_id,
                    "league_id": "428.l.41083",
                    "team_name": user_team_name or "Unknown Team",
                    "team_id": user_team_id or "",
                    "league_name": league_name,
                    "created_at": datetime.now().isoformat(),
                }

                # Check if league already exists for this user
                existing_league = yahoo_league_repo.get_by_league_id("428.l.41083")
                if existing_league:
                    # No updates after first insert
                    db_message = "League exists - no update performed"
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
                return (
                    f"<h2>Error</h2><p>Failed to process debug league sync: {str(e)}</p><br><a href='/dashboard'>← Back to Dashboard</a>",
                    500,
                )
        
        return yahoo_bp
    
    def get_bp(self):
        return self._blueprint