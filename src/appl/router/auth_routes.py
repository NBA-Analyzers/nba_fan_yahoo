import time
import xml.etree.ElementTree as ET

from ..config.app_config import DEBUG
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from flask import Blueprint, current_app, redirect, session, url_for
from ..middleware.auth_decorators import require_google_auth
from ..repository.supaBase.models.google_auth import GoogleAuth
from ..repository.supaBase.models.google_fantasy import GoogleFantasy
from ..repository.supaBase.models.yahoo_auth import YahooAuth
from ..repository.supaBase.services.auth_services import AuthService
from ..repository.supaBase.services.fantasy_services import FantasyService
from ..service.openai_file_manager import OpenaiFileManager


class AuthRouter:
    
    def __init__(self, openai_file_manager: OpenaiFileManager):
        self.openai_file_manager = openai_file_manager
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        
        auth_bp = Blueprint('auth', __name__, url_prefix="/auth")
        
        @auth_bp.route("/google/login")
        def google_login():
            """Google OAuth login - First step in authentication flow"""

            google = current_app.oauth.create_client("google")
            if google is None:
                print("ERROR: Google OAuth client is not available!")
                return "Google OAuth client not configured", 500

            # Always use HTTPS when behind ngrok proxy
            redirect_uri = url_for("auth.google_callback", _external=True, _scheme="https")
            return google.authorize_redirect(redirect_uri)

        @auth_bp.route("/google/callback")
        def google_callback():
            """Google OAuth callback - After successful Google auth, redirect to dashboard"""

            google = current_app.oauth.create_client("google")
            if google is None:
                print("ERROR: Google OAuth client is not available!")
                return "Google OAuth client not configured", 500

            try:
                token = google.authorize_access_token()
                resp = google.get("https://openidconnect.googleapis.com/v1/userinfo")
                user_info = resp.json()

                # Store user info in session
                session["google_user"] = user_info

                # Extract user data
                google_user_id = user_info["sub"]
                full_name = user_info["name"]
                email = user_info["email"]
                access_token = token["access_token"]

                # Create GoogleAuth object
                google_auth = GoogleAuth(
                    google_user_id=google_user_id,
                    full_name=full_name,
                    email=email,
                    access_token=access_token,
                )

                # Insert or update user in database using AuthService
                auth_service = AuthService()
                try:
                    created_user = auth_service.create_or_update_google_user(google_auth)
                    print(
                        f"✅ User successfully saved to database: {created_user.full_name}"
                    )
                except Exception as e:
                    print(f"❌ Database operation failed: {e}")
                    # Continue with login even if database fails

                # Redirect to dashboard instead of showing user info directly
                return redirect(url_for("main.dashboard"))

            except Exception as e:
                print(f"❌ Error during Google callback: {e}")
                return "Google login failed. Please try again.", 500

        @auth_bp.route("/yahoo/login")
        @require_google_auth
        def yahoo_login():
            """Yahoo OAuth login - Requires Google authentication first"""
            if DEBUG:
                return redirect("/yahoo/debug_league")

            yahoo = current_app.oauth.create_client("yahoo")

            # Always use HTTPS when behind ngrok proxy, same as Google login
            redirect_uri = url_for("auth.yahoo_callback", _external=True, _scheme="https")
            return yahoo.authorize_redirect(redirect_uri=redirect_uri)

        @auth_bp.route("/yahoo/callback")
        @require_google_auth
        def yahoo_callback():
            """Yahoo OAuth callback - Requires Google authentication first"""
            try:
                yahoo = current_app.oauth.create_client("yahoo")
                token = yahoo.authorize_access_token()
                user_guid = token.get("xoauth_yahoo_guid")

                if not user_guid:
                    resp = yahoo.get("fantasy/v2/users;use_login=1", token=token)
                    root = ET.fromstring(resp.text)
                    ns = {"ns": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
                    guid_elem = root.find(".//ns:guid", ns)
                    if guid_elem is None:
                        return "Could not retrieve user GUID", 500
                    user_guid = guid_elem.text

                username = None
                try:
                    # Option 1: Try to get from token (some Yahoo responses include profile)
                    if "profile" in token and "nickname" in token["profile"]:
                        username = token["profile"]["nickname"]
                    # Option 2: Fetch from Yahoo API
                    else:
                        resp = yahoo.get("fantasy/v2/users;use_login=1", token=token)
                        root = ET.fromstring(resp.text)
                        ns = {
                            "ns": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"
                        }
                        nickname_elem = root.find(".//ns:nickname", ns)
                        if nickname_elem is not None:
                            username = nickname_elem.text
                except Exception as e:
                    print(f"⚠️ Could not fetch username: {e}")
                # Initialize token store in session if it doesn't exist
                if "token_store" not in session:
                    session["token_store"] = {}

                # Store tokens in session and token store
                session["token_store"][user_guid] = {
                    "access_token": token["access_token"],
                    "refresh_token": token["refresh_token"],
                    "expires_at": time.time() + token["expires_in"],
                    "guid": user_guid,
                    "username": username,
                }

                session["user"] = user_guid

                # Create YahooAuth object for database insertion
                yahoo_auth = YahooAuth(
                    yahoo_user_id=user_guid,
                    access_token=token["access_token"],
                    refresh_token=token["refresh_token"],
                    username=username,
                )

                # Insert or update user in database using AuthService
                auth_service = AuthService()
                try:
                    auth_service.create_or_update_yahoo_user(yahoo_auth)
                except Exception as e:
                    print(f"❌ Database operation failed: {e}")
                    # Continue with login even if database fails

                google_user_info = session.get("google_user", {})
                google_user_id = google_user_info.get("sub")

                if google_user_id:
                    try:
                        # Create the fantasy connection
                        google_fantasy = GoogleFantasy(
                            google_user_id=google_user_id,
                            fantasy_user_id=user_guid,  # This is the Yahoo user ID
                            fantasy_platform="yahoo",
                        )

                        # Use FantasyService to create the connection
                        fantasy_service = FantasyService()
                        fantasy_connection = fantasy_service.connect_fantasy_platform(
                            google_fantasy
                        )

                        # Store connection info in session for reference
                        session["fantasy_connected"] = True
                        session["fantasy_connection_created_at"] = (
                            fantasy_connection.created_at
                        )

                    except Exception as e:
                        print(f"❌ Unexpected error creating fantasy connection: {str(e)}")
                else:
                    print(
                        "❌ Could not find Google user ID in session for fantasy connection"
                    )

                # Get leagues for selection

                yahoo_service = YahooService(
                    session["token_store"], self.openai_file_manager
                )
                league_options = yahoo_service.get_user_leagues(user_guid)

                # Get Google user info for personalization
                user_info = session.get("google_user", {})
                user_name = user_info.get("name", "User")

                # Build league options HTML dynamically
                league_html = ""
                if league_options and len(league_options) > 0:
                    for league in league_options:
                        league_html += f'<input type="radio" name="league_id" value="{league.get("id", "")}" required> {league.get("name", "Unknown League")}<br>'
                else:
                    league_html = (
                        "<p>No leagues found. Please check your Yahoo account.</p>"
                    )

                # Render a simple HTML form for league selection
                html = f"""
                <h2>Hello {user_name}!</h2>
                <h3>Your Yahoo Fantasy Leagues</h3>
                <p>Yahoo account connected successfully! Select your league:</p>
                <form id="leagueForm" action="/yahoo/select_league" method="post">
                    {league_html}
                    <br>
                    <button type="submit" id="submitBtn">
                        <span id="btnText">Connect League & Go to AI Chat</span>
                        <span id="loadingSpinner" style="display: none;">⏳ Loading...</span>
                    </button>
                </form>
                <br>
                <a href="/dashboard">← Back to Dashboard</a>
                """
                return html

            except Exception as e:
                print(f"❌ Error during Yahoo callback: {e}")
                return "Yahoo login failed. Please try again.", 500

        @auth_bp.route("/logout")
        def logout():
            """Logout and clear session"""
            session.clear()
            return redirect("/")

        return auth_bp
    
    def get_bp(self):
        return self._blueprint