import time
import xml.etree.ElementTree as ET

from ..config.app_config import DEBUG, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from flask import Blueprint, current_app, redirect, render_template, session, url_for
from ..middleware.auth_decorators import require_google_auth
from ..repository.supaBase.models.google_auth import GoogleAuth
from ..repository.supaBase.models.google_fantasy import GoogleFantasy
from ..repository.supaBase.models.yahoo_auth import YahooAuth
from ..repository.supaBase.services.auth_services import AuthService
from ..repository.supaBase.services.fantasy_services import FantasyService
from ..ai.document_indexer import DocumentIndexer

def get_user_guid_from_token(token, yahoo):
    user_guid = token.get("xoauth_yahoo_guid")

    if not user_guid:
        resp = yahoo.get("fantasy/v2/users;use_login=1", token=token)
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            root = None
        ns = {"ns": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
        guid_elem = root.find(".//ns:guid", ns) if root is not None else None
        if guid_elem is None:
            raise RuntimeError(
                f"Could not retrieve Yahoo user GUID (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        user_guid = guid_elem.text

    return user_guid

def get_username_from_token(token, yahoo):
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
    
    return username


class AuthRouter:
    
    def __init__(self, document_indexer: DocumentIndexer):
        self.document_indexer = document_indexer
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
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                print("ERROR: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set in .env")
                return "Google OAuth credentials not configured", 500

            # ProxyFix already reports https behind ngrok; forcing it breaks plain http://localhost
            redirect_uri = url_for("auth.google_callback", _external=True)
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
                return render_template(
                    "pages/message.html",
                    title="Sign-in didn't work",
                    text="Something went wrong signing in with Google. Please try again.",
                    link="/auth/google/login",
                    link_text="Try again",
                ), 500

        @auth_bp.route("/yahoo/login")
        @require_google_auth
        def yahoo_login():
            """Yahoo OAuth login - Requires Google authentication first"""
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
                
                user_guid = get_user_guid_from_token(token, yahoo)

                username = get_username_from_token(token, yahoo)

                
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
                    session["token_store"], self.document_indexer
                )
                league_options = yahoo_service.get_user_leagues(user_guid)

                return render_template("pages/choose_league.html", leagues=league_options or [])

            except Exception as e:
                print(f"❌ Error during Yahoo callback: {e}")
                return render_template(
                    "pages/message.html",
                    title="Yahoo didn't connect",
                    text="Something went wrong talking to Yahoo. Please try again.",
                    link="/auth/yahoo/login",
                    link_text="Try again",
                ), 500

        @auth_bp.route("/logout")
        def logout():
            """Logout and clear session"""
            session.clear()
            return redirect("/")

        return auth_bp
    
    def get_bp(self):
        return self._blueprint