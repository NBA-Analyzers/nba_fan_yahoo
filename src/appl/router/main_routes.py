from flask import (
    Blueprint,
    request,
    render_template,
    session,
    redirect,
    url_for,
    jsonify,
)
import time
import uuid
import logging

from ..ai.document_indexer import DocumentIndexer
from ..draft.manual_league import user_key
from ..season.service import index_manual_league_async, manual_chat_id
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from ..middleware.auth_decorators import require_google_auth

logger = logging.getLogger(__name__)


class MainRouter:
    def __init__(self, document_indexer: DocumentIndexer, manual_store=None):
        self.document_indexer = document_indexer
        self.manual_store = manual_store
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        main_bp = Blueprint("main", __name__)

        @main_bp.route("/")
        def homepage():
            """Main homepage with login options"""
            # Check if user is already logged in with Google
            if "google_user" in session:
                return redirect(url_for("main.dashboard"))

            return render_template("pages/home.html")

        @main_bp.route("/dashboard")
        def dashboard():
            """Dashboard page after Google authentication - shows Yahoo login option"""

            @require_google_auth
            def dashboard_content():
                user_info = session.get("google_user", {})
                first_name = (user_info.get("given_name") or user_info.get("name") or "there").split()[0]

                # Check if user also has Yahoo authentication
                yahoo_authenticated = "user" in session and session[
                    "user"
                ] in session.get("token_store", {})

                # Get user's synced leagues if they have Yahoo auth
                leagues, leagues_error = [], False
                if yahoo_authenticated:
                    try:
                        yahoo_service = YahooService(
                            session["token_store"], self.document_indexer
                        )
                        leagues = yahoo_service.get_user_synced_leagues(session["user"]) or []
                    except Exception as e:
                        print(f"Error getting synced leagues: {e}")
                        leagues_error = True

                return render_template(
                    "pages/dashboard.html",
                    first_name=first_name,
                    yahoo_connected=yahoo_authenticated,
                    leagues=leagues,
                    leagues_error=leagues_error,
                )

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
                            session["token_store"], self.document_indexer
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

        @main_bp.route("/ai-chat/manual/<league_id>")
        @require_google_auth
        def ai_chat_manual(league_id):
            """The same chat for a manual league. Its data is indexed in the background
            (like the Yahoo sync) while the chat opens."""
            try:
                league = self.manual_store.get(user_key(session.get("google_user")), league_id)
            except KeyError:
                return redirect("/manual")
            try:
                index_manual_league_async(self.document_indexer, league)
            except Exception as e:
                logger.warning(f"Could not start indexing manual league {league_id}: {e}")
            return redirect(f"/agent?league_id={manual_chat_id(league_id)}&session_id={uuid.uuid4()}")

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
