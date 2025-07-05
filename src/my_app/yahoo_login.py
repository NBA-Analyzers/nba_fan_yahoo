from flask import Flask, redirect, request, session, url_for, jsonify, render_template_string
from authlib.integrations.flask_client import OAuth
import os
import time
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from dotenv import load_dotenv

from azure.azure_blob_storage import AzureBlobStorage
from fantasy_platforms_integration.yahoo.sync_yahoo_league import YahooLeague


load_dotenv(".env") # Loads from .env or .env.vault if DOTENV_KEY is set

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "supersecret")
app.config.update(
    SESSION_COOKIE_SAMESITE=None,
    SESSION_COOKIE_SECURE=True
)
print("✓ Flask session configuration set")

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Configuration (replace with your Yahoo app info)
YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID")
YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URL")

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
yahoo_game = None

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
    if DEBUG:
        return redirect('/debug_league')

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

    sc = CustomYahooSession(token_store[user_guid])
    yahoo_game = yfa.Game(sc, 'nba')

    yahoo_game = get_yahoo_sdk()
    
    league_ids = yahoo_game.league_ids()
    league_options = []
    for league_id in league_ids:
        league = yahoo_game.to_league(league_id)
        league_name = league.settings()['name']
        league_options.append({'id': league_id, 'name': league_name})

    # Render a simple HTML form for league selection
    html = '''
    <h2>Select Your League</h2>
    <form action="/select_league" method="post">
        {% for league in leagues %}
            <input type="radio" name="league_id" value="{{ league.id }}" required> {{ league.name }}<br>
        {% endfor %}
        <button type="submit">Continue</button>
    </form>
    '''
    return render_template_string(html, leagues=league_options)

@app.route('/select_league', methods=['POST'])
def select_league():
    if DEBUG:
        sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
        yahoo_game = yfa.Game(sc, 'nba')
        league = yahoo_game.to_league('428.l.41083')
        yahoo_league = YahooLeague(league)
        results = yahoo_league.sync_full_league(azure_blob_storage=AzureBlobStorage(container_name="fantasy1"))
        return f"You synced: {results}" 


    league_id = request.form['league_id']
    yahoo_game = get_yahoo_sdk()
    league = yahoo_game.to_league(league_id)

    yahoo_league = YahooLeague(league)
    results = yahoo_league.sync_full_league()

    return f"You synced: {results}"  # Display the selected league name

@app.route('/debug_league')
def debug_league():
    sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    league = yahoo_game.to_league('428.l.41083')
    yahoo_league = YahooLeague(league)
    results = yahoo_league.sync_full_league()
    return f"You synced: {results}"  # Display the selected league name

def get_yahoo_sdk() -> yfa.Game:
    """
    Returns an authenticated yahoo_fantasy_api.Game object for the current user session.
    Returns None if the user is not authenticated or token is missing.
    """
    user_guid = session.get('user')
    if not user_guid or user_guid not in token_store:
        return None
    sc = CustomYahooSession(token_store[user_guid])
    return yfa.Game(sc, 'nba')

if __name__ == '__main__':
    print("=== Starting Flask development server ===")
    print("✓ App will run on http://localhost:5001")
    print("✓ Debug mode: ON")
    app.run(debug=True, host='0.0.0.0',  use_reloader=False, port=5001)
