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
from ..config.app_config import FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID
from ..identity.session import current_profile, current_user_id
from ..season.service import index_manual_league_async, manual_chat_id
from ..fantasy_integrations.espn.espn_service import EspnService, espn_chat_id
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from ..middleware.auth_decorators import require_login

logger = logging.getLogger(__name__)


def firebase_config():
    """Public Firebase web config for the sign-in widget, or None to use the old Google link."""
    if not (FIREBASE_API_KEY and FIREBASE_AUTH_DOMAIN):
        return None
    return {"apiKey": FIREBASE_API_KEY, "authDomain": FIREBASE_AUTH_DOMAIN,
            "projectId": FIREBASE_PROJECT_ID}


class MainRouter:
    def __init__(self, document_indexer: DocumentIndexer, manual_store=None, espn_service=None):
        self.document_indexer = document_indexer
        self.manual_store = manual_store
        self.espn_service = espn_service or EspnService(document_indexer)
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        main_bp = Blueprint("main", __name__)

        @main_bp.route("/")
        def homepage():
            """Main homepage with login options"""
            # Check if user is already logged in with Google
            if "user_id" in session:
                return redirect(url_for("main.dashboard"))

            return render_template("pages/home.html", firebase=firebase_config())

        @main_bp.route("/dashboard")
        def dashboard():
            """Dashboard page after Google authentication - shows Yahoo login option"""

            @require_login
            def dashboard_content():
                user_info = current_profile()
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

                manual_leagues = []
                if self.manual_store is not None:
                    try:
                        manual_leagues = self.manual_store.list(current_user_id())
                    except Exception as e:
                        logger.warning(f"Could not list manual leagues: {e}")

                espn_leagues = self.espn_service.get_user_leagues(current_user_id())

                return render_template(
                    "pages/dashboard.html",
                    first_name=first_name,
                    espn_leagues=espn_leagues,
                    yahoo_connected=yahoo_authenticated,
                    leagues=leagues,
                    leagues_error=leagues_error,
                    manual_leagues=manual_leagues,
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

            @require_login
            def chat_content():
                user_info = current_profile()
                user_guid = session.get("user")

                # Verify Yahoo authentication
                yahoo_authenticated = "user" in session and session[
                    "user"
                ] in session.get("token_store", {})

                if not yahoo_authenticated:
                    return redirect(url_for("main.dashboard"))

                # ========== TRIGGER NON-BLOCKING BACKGROUND SYNC ========== #
                # The chat loads immediately; a stale league (TTL) refreshes in a thread.
                # On Cloud Run this needs CPU always allocated (--no-cpu-throttling),
                # see docs/DEPLOY_CLOUD_RUN.md, or the thread stalls after the response.
                try:
                    if user_guid and "token_store" in session:
                        yahoo_service = YahooService(
                            session["token_store"], self.document_indexer
                        )
                        yahoo_service.sync_league_data_async(league_id, user_guid)
                        logger.info(f"Background sync triggered for league {league_id}")
                except Exception as e:
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
        @require_login
        def ai_chat_manual(league_id):
            """The same chat for a manual league. Its data is indexed in the background
            (like the Yahoo sync) while the chat opens."""
            try:
                league = self.manual_store.get(current_user_id(), league_id)
            except KeyError:
                return redirect("/manual")
            try:
                index_manual_league_async(self.document_indexer, league)
            except Exception as e:
                logger.warning(f"Could not start indexing manual league {league_id}: {e}")
            return redirect(f"/agent?league_id={manual_chat_id(league_id)}&session_id={uuid.uuid4()}")

        @main_bp.route("/ai-chat/espn/<league_id>")
        @require_login
        def ai_chat_espn(league_id):
            """The same chat for an ESPN league; it refreshes its data in the background
            (TTL, like the Yahoo sync) while the chat opens."""
            user_id = current_user_id()
            if not self.espn_service.league_repo.league_exist_for_user(league_id, user_id):
                return redirect(url_for("main.dashboard"))
            try:
                self.espn_service.sync_league_data_async(user_id, league_id)
            except Exception as e:
                logger.warning(f"Could not start syncing ESPN league {league_id}: {e}")
            return redirect(f"/agent?league_id={espn_chat_id(league_id)}&session_id={uuid.uuid4()}")

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
