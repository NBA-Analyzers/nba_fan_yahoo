from ..ai.document_indexer import DocumentIndexer
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import (
    YahooService,
    get_yahoo_sdk,
)
from flask import Blueprint, redirect, render_template, request, session, url_for
from ..middleware.auth_decorators import require_login


def _problem(title, text):
    return render_template("pages/message.html", title=title, text=text), 500


class YahooRouter:
    
    def __init__(self, document_indexer: DocumentIndexer):
        self.document_indexer = document_indexer
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        
        yahoo_bp = Blueprint("yahoo", __name__, url_prefix="/yahoo")

        @yahoo_bp.route("/select_league", methods=["POST"])
        @require_login
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

        return yahoo_bp
    
    def get_bp(self):
        return self._blueprint