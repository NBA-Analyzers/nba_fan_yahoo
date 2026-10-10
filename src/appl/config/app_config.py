import os

# .env is loaded once, by the appl package (appl/__init__.py)


def configure_app(app):
    """Configure Flask app with settings"""
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY is not set; session cookies would be forgeable")
    app.config['SECRET_KEY'] = secret_key
    # Lax: OAuth callbacks are top-level GET navigations, which still carry the cookie;
    # cross-site POSTs don't. Secure on Cloud Run (K_SERVICE is set) or when
    # SESSION_COOKIE_SECURE=1 (e.g. behind an https tunnel); plain http://localhost works.
    secure = bool(os.getenv("K_SERVICE")) or os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true")
    app.config.update(
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure,
        SESSION_COOKIE_HTTPONLY=True,
    )
    # Session data lives on the server (Firestore on Cloud Run, memory elsewhere); the
    # cookie only holds a random id.
    from .server_session import build_session_interface

    app.session_interface = build_session_interface()
    print("✓ Flask session configuration set")

# Environment variables
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID") or os.getenv("YAHOO_FANTASY_CLIENT_ID")
YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET") or os.getenv("YAHOO_FANTASY_CLIENT_SECRET")
YAHOO_REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("Google_OAuth_Client_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("Google_OAuth_Client_Secret")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")  # public by design (identifies the project)
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
