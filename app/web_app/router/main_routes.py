import logging
import time
import uuid

from fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from middleware.auth_decorators import require_google_auth

from common.openai_file_manager import OpenaiFileManager

logger = logging.getLogger(__name__)


class MainRouter:
    def __init__(self, openai_file_manager: OpenaiFileManager):
        self.openai_file_manager = openai_file_manager
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        main_bp = Blueprint("main", __name__)

        @main_bp.route("/")
        def homepage():
            """Main homepage with login options"""
            # Check if user is already logged in with Google
            if "google_user" in session:
                return redirect(url_for("main.dashboard"))

            # Show homepage with login options
            return """
            <h1>Fantasy League App</h1>
            <p>Welcome! Please login to get started:</p>
            <ul>
                <li><a href="/auth/google/login">Login with Google</a></li>
            </ul>
            <hr>
            <p>Other options:</p>
            <ul>
                <li><a href="/api/sync_league">Sync League (Debug)</a></li>
                <li><a href="/health">Health Check</a></li>
            </ul>
            """

        @main_bp.route("/dashboard")
        def dashboard():
            """Dashboard page after Google authentication - shows Yahoo login option"""

            @require_google_auth
            def dashboard_content():
                user_info = session.get("google_user", {})
                user_name = user_info.get("name", "User")

                # Check if user also has Yahoo authentication
                yahoo_authenticated = "user" in session and session[
                    "user"
                ] in session.get("token_store", {})

                # Get user's synced leagues if they have Yahoo auth
                synced_leagues_html = ""
                if yahoo_authenticated:
                    try:
                        yahoo_service = YahooService(
                            session["token_store"], self.openai_file_manager
                        )
                        user_leagues = yahoo_service.get_user_synced_leagues(
                            session["user"]
                        )

                        if user_leagues:
                            # Build league HTML dynamically
                            league_items = []
                            for league in user_leagues:
                                league_items.append(f"""
                                <div style="border: 1px solid #dee2e6; padding: 15px; margin: 10px 0; border-radius: 8px; background: white;">
                                    <h4>League: {league.get("league_id", "Unknown")}</h4>
                                    <p><strong>Team:</strong> {league.get("team_name", "Unknown Team")}</p>
                                    <p><strong>Added:</strong> {league.get("created_at", "Unknown")}</p>
                                    <a href="/ai-chat/{league.get("league_id", "unknown")}" style="background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-size: 14px;">AI Chat</a>
                                </div>
                                """)

                            synced_leagues_html = f"""
                            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                                <h3>Your Synced Leagues</h3>
                                <p>Click on any league to access its AI Assistant:</p>
                                {"".join(league_items)}
                            </div>
                            """
                        else:
                            synced_leagues_html = """
                            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                                <h3>Your Synced Leagues</h3>
                                <p>No leagues synced yet. Connect your Yahoo account to get started!</p>
                            </div>
                            """
                    except Exception as e:
                        print(f"Error getting synced leagues: {e}")
                        synced_leagues_html = """
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <h3>Your Synced Leagues</h3>
                            <p>Error loading leagues. Please try refreshing the page.</p>
                        </div>
                        """

                html = f"""
                <h1>Welcome, {user_name}!</h1>
                <p>You are logged in with Google.</p>
                
                <h2>Connect to Yahoo Fantasy</h2>
                <p>To access your fantasy leagues, please connect your Yahoo account:</p>
                
                {"<p>Yahoo account connected!</p>" if yahoo_authenticated else ""}
                
                <ul>
                    <li><a href="/auth/yahoo/login">{"Re-connect" if yahoo_authenticated else "Connect"} Yahoo Account</a></li>
                    {'<li><a href="/yahoo/my_leagues">View My Synced Leagues</a></li>' if yahoo_authenticated else ""}
                    <li><a href="/api/sync_league">Sync League (Debug)</a></li>
                    <li><a href="/health">Health Check</a></li>
                    <li><a href="/auth/logout">Logout</a></li>
                </ul>
                
                {synced_leagues_html}
                """

                return html

            return dashboard_content()

        @main_bp.route("/health")
        def health_check():
            """Health check endpoint"""
            return jsonify(
                {
                    "status": "healthy",
                    "service": "Fantasy League App",
                    "timestamp": time.time(),
                }
            )

        @main_bp.route("/ai-chat/<league_id>")
        def ai_chat(league_id):
            """AI Chat interface for a specific league - triggers background data sync"""

            logger = logging.getLogger(__name__)

            @require_google_auth
            def chat_content():
                user_info = session.get("google_user", {})
                user_guid = session.get("user")

                # Verify Yahoo authentication
                yahoo_authenticated = "user" in session and session[
                    "user"
                ] in session.get("token_store", {})

                if not yahoo_authenticated:
                    return redirect(url_for("main.dashboard"))

                # ========== TRIGGER NON-BLOCKING BACKGROUND SYNC ========== #
                # This happens in the background while the chat loads immediately
                try:
                    print(f"\n{'=' * 60}")
                    print(f"🔄 Triggering background sync for league: {league_id}")
                    print(f"{'=' * 60}\n")

                    if user_guid and "token_store" in session:
                        yahoo_service = YahooService(
                            session["token_store"], self.openai_file_manager
                        )

                        # ✨ NEW: Start background sync (non-blocking)
                        yahoo_service.sync_league_data_async(league_id, user_guid)

                        print(f"✅ Background sync thread started!")
                        print(
                            f"   Chat will load immediately while data updates in background"
                        )
                        logger.info(f"Background sync triggered for league {league_id}")
                except Exception as e:
                    print(f"⚠️ Could not start background sync: {str(e)}")
                    logger.warning(
                        f"Could not trigger sync for league {league_id}: {e}"
                    )
                    # Don't block the user - let them use the chat with existing data

                # ========== RENDER CHAT IMMEDIATELY (DON'T WAIT FOR SYNC) ========== #

                # Generate unique session ID
                session_id = str(uuid.uuid4())

                # Redirect to the FastAPI /agent endpoint with query parameters
                agent_url = f"/agent?league_id={league_id}&session_id={session_id}"
                return redirect(agent_url)

            return chat_content()

        # Serve the main page
        @main_bp.route("/agent")
        async def read_index():
            return render_template(
                "index.html",
                request=request,
                league_id=request.args.get("league_id"),
                session_id=request.args.get("session_id"),
            )

        return main_bp

    def get_bp(self):
        return self._blueprint
