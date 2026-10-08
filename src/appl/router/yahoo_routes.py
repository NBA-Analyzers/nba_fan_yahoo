from datetime import datetime

import yahoo_fantasy_api as yfa
from ..ai.document_indexer import DocumentIndexer
from ..config.app_config import DEBUG
from ..fantasy_integrations.yahoo.sync_league.sync_yahoo_league import YahooLeague
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import (
    YahooService,
    get_yahoo_sdk,
)
from flask import Blueprint, redirect, render_template, request, session, url_for
from ..middleware.auth_decorators import require_google_auth
from ..repository.supaBase.repositories.yahoo_league_repository import (
    YahooLeagueRepository,
)
from yahoo_oauth import OAuth2


def _problem(title, text):
    return render_template("pages/message.html", title=title, text=text), 500


class YahooRouter:
    
    def __init__(self, document_indexer: DocumentIndexer):
        self.document_indexer = document_indexer
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        
        yahoo_bp = Blueprint("yahoo", __name__, url_prefix="/yahoo")

        @yahoo_bp.route("/select_league", methods=["POST"])
        @require_google_auth
        def select_league():
            """Handle league selection - Requires Google authentication first"""
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
                yahoo_service = YahooService(session["token_store"], self.document_indexer)
                result = yahoo_service.sync_league_data(league_id, user_guid)

                if "error" in result:
                    return _problem("We couldn't sync that league", result["error"])

                # Get league name for the redirect
                try:
                    yahoo_game = get_yahoo_sdk(session["token_store"], {"user": user_guid})
                    league = yahoo_game.to_league(league_id)
                    league_settings = league.settings()
                    league_name = league_settings.get("name", "Unknown League")
                except Exception:
                    league_name = "Unknown League"

                return render_template(
                    "pages/league_ready.html", league_id=league_id, league_name=league_name
                )

            except Exception as e:
                print(f"❌ Error during league selection: {e}")
                return _problem("We couldn't sync that league", "Something went wrong. Please try again in a moment.")


        @yahoo_bp.route("/my_leagues")
        def my_leagues():
            """Synced leagues now live on the dashboard"""
            return redirect(url_for("main.dashboard"))


        @yahoo_bp.route("/debug_league")
        @require_google_auth
        def debug_league():
            """Debug endpoint for league sync - Requires Google authentication first"""
            try:
                sc = OAuth2(
                    None,
                    None,
                    from_file="src/a/fantasy_platforms_integration/yahoo/oauth22.json",
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