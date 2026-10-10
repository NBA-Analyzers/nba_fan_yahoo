from authlib.integrations.flask_client import OAuth
from .app_config import YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET

def configure_oauth(app):
    """Configure OAuth for the Flask app (Yahoo only; sign-in is Firebase Auth)"""
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
    
    return oauth
