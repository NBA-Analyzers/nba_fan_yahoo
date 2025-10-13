from authlib.integrations.flask_client import OAuth
from .app_config import YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_DISCOVERY_URL

def configure_oauth(app):
    """Configure OAuth for the Flask app"""
    oauth = OAuth(app)
    
    # Yahoo OAuth
    oauth.register(
        name='yahoo',
        client_id=YAHOO_CLIENT_ID,
        client_secret=YAHOO_CLIENT_SECRET,
        access_token_url='https://api.login.yahoo.com/oauth2/get_token',
        authorize_url='https://api.login.yahoo.com/oauth2/request_auth',
        api_base_url='https://fantasysports.yahooapis.com/',
        client_kwargs={
            'scope': 'fspt-w',
        }
    )
    
    # Google OAuth
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,    
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    return oauth
