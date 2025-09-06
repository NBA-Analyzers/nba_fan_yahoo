import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2

class CustomYahooSession:
    def __init__(self, token_data):
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token')
        self.token_type = token_data.get('token_type', 'bearer')
        self.token = token_data
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f"Bearer {self.access_token}"
        })

class ManualOAuth2(OAuth2):
    def __init__(self, token_data, consumer_key, consumer_secret):
        self.token = token_data
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token')
        self.token_type = token_data.get('token_type', 'bearer')
        self.expires_at = token_data.get('expires_at')
        self.session_handle = token_data.get('session_handle')
        self.guid = token_data.get('xoauth_yahoo_guid') or token_data.get('guid')
        self.session = requests.Session()
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f"Bearer {self.access_token}"
        })

        self.token = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_type': self.token_type,
            'expires_in': 3600
        }

def get_yahoo_sdk(token_store, session):
    """
    Returns an authenticated yahoo_fantasy_api.Game object for the current user session.
    Returns None if the user is not authenticated or token is missing.
    """
    user_guid = session.get('user')
    if not user_guid or user_guid not in token_store:
        return None
    sc = CustomYahooSession(token_store[user_guid])
    return yfa.Game(sc, 'nba')
