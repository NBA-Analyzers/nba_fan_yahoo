import logging
import time
import xml.etree.ElementTree as ET

from ..config.app_config import DEBUG, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from ..fantasy_integrations.yahoo.sync_league.yahoo_service import YahooService
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from ..middleware.auth_decorators import require_login
from ..identity import FirestoreIdentityStore, UnverifiedEmail, sign_in
from ..identity.firebase_verify import InvalidToken, verify_id_token
from ..identity.session import current_user_id, rotate_session, start_session
from ..repository.firestore import (
    AuthService,
    FantasyService,
    GoogleFantasy,
    YahooAuth,
    retry_once,
)
from ..ai.document_indexer import DocumentIndexer
from ..ai.redact import scrub_secrets

logger = logging.getLogger(__name__)


def log_failure(what: str, exc: Exception) -> None:
    """Log the exception type and a scrubbed message. Never the traceback or raw
    response bodies: OAuth errors can echo tokens."""
    logger.error("%s: %s: %s", what, type(exc).__name__, scrub_secrets(str(exc))[:300])

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
        log_failure("Could not fetch the Yahoo username", e)
    
    return username


class AuthRouter:
    
    def __init__(self, document_indexer: DocumentIndexer, identity_store=None, auth_service=None,
                 token_verifier=None):
        self.document_indexer = document_indexer
        self.identity_store = identity_store or FirestoreIdentityStore()
        self.auth_service = auth_service or AuthService()
        self.token_verifier = token_verifier or verify_id_token
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        
        auth_bp = Blueprint('auth', __name__, url_prefix="/auth")
        
        @auth_bp.route("/session", methods=["POST"])
        def create_session():
            """Sign in with a Firebase ID token (email+password, email link or Google).
            The browser signs in with the Firebase SDK; here the token is verified and
            turned into our own user_id and a server-side session."""
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="bad_origin"), 403
            body = request.get_json(silent=True) or {}
            token = body.get("idToken")
            if not isinstance(token, str) or not token:
                return jsonify(error="missing_token"), 400
            try:
                claims = self.token_verifier(token)
            except InvalidToken as e:
                log_failure("Rejected sign-in token", e)
                return jsonify(error="invalid_token"), 401
            try:
                signed_in = sign_in(self.identity_store, claims)
            except UnverifiedEmail:
                return jsonify(error="verify_email"), 403
            start_session(signed_in["user_id"], signed_in["profile"])
            return jsonify(ok=True, redirect=url_for("main.dashboard"))

        @auth_bp.route("/google/login")
        def google_login():
            """Google OAuth login - First step in authentication flow"""

            google = current_app.oauth.create_client("google")
            if google is None:
                logger.error("Google OAuth client is not available")
                return "Google OAuth client not configured", 500
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                logger.error("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
                return "Google OAuth credentials not configured", 500

            # ProxyFix already reports https behind ngrok; forcing it breaks plain http://localhost
            redirect_uri = url_for("auth.google_callback", _external=True)
            return google.authorize_redirect(redirect_uri)

        @auth_bp.route("/google/callback")
        def google_callback():
            """Google OAuth callback - After successful Google auth, redirect to dashboard"""

            google = current_app.oauth.create_client("google")
            if google is None:
                logger.error("Google OAuth client is not available")
                return "Google OAuth client not configured", 500

            try:
                token = google.authorize_access_token()
                resp = google.get("https://openidconnect.googleapis.com/v1/userinfo")
                user_info = resp.json()

                # Google's userinfo has the same shape as the claims of a Firebase ID token
                sub = user_info["sub"]
                claims = {
                    "uid": sub,
                    "email": user_info.get("email"),
                    "email_verified": user_info.get("email_verified"),
                    "name": user_info.get("name"),
                    "given_name": user_info.get("given_name"),
                    "picture": user_info.get("picture"),
                    "firebase": {"sign_in_provider": "google.com",
                                 "identities": {"google.com": [sub]}},
                }
                # A storage failure falls back to the Google sub and doesn't block login
                signed_in = sign_in(self.identity_store, claims)
                start_session(signed_in["user_id"], signed_in["profile"])
                try:  # kept server-side with the user; a failure never blocks login
                    retry_once(lambda: self.auth_service.save_google_token(
                        signed_in["user_id"], token["access_token"]), "saving Google token")
                except Exception as e:
                    log_failure("Could not save the Google token", e)
                return redirect(url_for("main.dashboard"))

            except Exception as e:
                log_failure("Error during Google callback", e)
                return render_template(
                    "pages/message.html",
                    title="Sign-in didn't work",
                    text="Something went wrong signing in with Google. Please try again.",
                    link="/auth/google/login",
                    link_text="Try again",
                ), 500

        @auth_bp.route("/yahoo/login")
        @require_login
        def yahoo_login():
            """Yahoo OAuth login - Requires Google authentication first"""
            yahoo = current_app.oauth.create_client("yahoo")

            # Always use HTTPS when behind ngrok proxy, same as Google login
            redirect_uri = url_for("auth.yahoo_callback", _external=True, _scheme="https")
            return yahoo.authorize_redirect(redirect_uri=redirect_uri)

        @auth_bp.route("/yahoo/callback")
        @require_login
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

                # Tokens are secrets: only the error is logged, never the tokens. A storage
                # failure must not stop the connection, the tokens are also in the session.
                try:
                    retry_once(lambda: self.auth_service.create_or_update_yahoo_user(YahooAuth(
                        yahoo_user_id=user_guid,
                        access_token=token["access_token"],
                        refresh_token=token["refresh_token"],
                        username=username,
                    )), "saving Yahoo login")
                    # Idempotent, so reconnecting later refreshes the link without errors
                    FantasyService().connect_fantasy_platform(GoogleFantasy(
                        google_user_id=current_user_id(),
                        fantasy_user_id=user_guid,
                        fantasy_platform="yahoo",
                    ))
                    session["fantasy_connected"] = True
                except Exception as e:
                    log_failure("Could not save the Yahoo connection", e)
                rotate_session()

                # Get leagues for selection
                yahoo_service = YahooService(
                    session["token_store"], self.document_indexer
                )
                league_options = yahoo_service.get_user_leagues(user_guid)

                return render_template("pages/choose_league.html", leagues=league_options or [])

            except Exception as e:
                log_failure("Error during Yahoo callback", e)
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