import os
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
load_dotenv(env_path)

def configure_app(app):
    """Configure Flask app with settings"""
    app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "supersecret")
    app.config.update(
        SESSION_COOKIE_SAMESITE=None,
        SESSION_COOKIE_SECURE=True
    )
    print("✓ Flask session configuration set")

# Environment variables
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID") or os.getenv("YAHOO_FANTASY_CLIENT_ID")
YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET") or os.getenv("YAHOO_FANTASY_CLIENT_SECRET")
YAHOO_REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("Google_OAuth_Client_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("Google_OAuth_Client_Secret")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
