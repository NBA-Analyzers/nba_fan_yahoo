from flask import Flask, redirect, request, session, url_for, jsonify
from authlib.integrations.flask_client import OAuth
import os
import time
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "supersecret")
app.config.update(
    SESSION_COOKIE_SAMESITE=None,
    SESSION_COOKIE_SECURE=True
)
print("✓ Flask session configuration set")

# Configuration (replace with your Yahoo app info)
YAHOO_CLIENT_ID = "dj0yJmk9Vmx3STVwNzVnNFVOJmQ9WVdrOU9UbDFabFU1V1dZbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTUw"
YAHOO_CLIENT_SECRET = "c6ecb8500877349e193025923afce04baf6fd315"
REDIRECT_URI = "https://ba5d-2a06-c701-4746-fb00-6014-7012-2470-529c.ngrok-free.app"  # Fixed: added protocol and correct port

# YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID")
# YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
# REDIRECT_URI = os.getenv("REDIRECT_URI")

oauth = OAuth(app)
yahoo = oauth.register(
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

token_store = {}

class CustomYahooSession:
    def __init__(self, token_data):
        import requests
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
        import requests
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

@app.route('/')
def homepage():
    return '<a href="/login">Login with Yahoo</a>'

@app.route('/login')
def login():
    return yahoo.authorize_redirect(redirect_uri=REDIRECT_URI + "/callback")

@app.route('/callback')
def callback():
    token = yahoo.authorize_access_token()
    user_guid = token.get('xoauth_yahoo_guid')

    if not user_guid:
        resp = yahoo.get('fantasy/v2/users;use_login=1', token=token)
        root = ET.fromstring(resp.text)
        ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
        guid_elem = root.find('.//ns:guid', ns)
        if guid_elem is None:
            return "Could not retrieve user GUID", 500
        user_guid = guid_elem.text

    token_store[user_guid] = {
        'access_token': token['access_token'],
        'refresh_token': token['refresh_token'],
        'expires_at': time.time() + token['expires_in'],
        'guid': user_guid
    }

    session['user'] = user_guid


# ✅ Usage:
    # sc = ManualOAuth2(token_store[user_guid], YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)
    sc = CustomYahooSession(token_store[user_guid])

    # sc.consumer_key = YAHOO_CLIENT_ID
    # sc.consumer_secret = YAHOO_CLIENT_SECRET
    # sc.token = {
    #     'access_token': token['access_token'],
    #     'refresh_token': token['refresh_token'],
    #     'token_type': 'bearer',
    #     'expires_in': 3600
    # }

    yahoo_game = yfa.Game(sc, 'nba')
    league_id = yahoo_game.league_ids()[0]
    league = yahoo_game.to_league(league_id)
    print(f"League object: {league}")
    # Example league ID
    return f"League: {league.team_key()}! <a href='/logout'>Logout</a>"

if __name__ == '__main__':
    print("=== Starting Flask development server ===")
    print("✓ App will run on http://localhost:5001")
    print("✓ Debug mode: ON")
    app.run(debug=True, host='0.0.0.0',  use_reloader=False, port=5001)
