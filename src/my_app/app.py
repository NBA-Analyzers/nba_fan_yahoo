from flask import Flask, redirect, request, session, url_for, jsonify, render_template_string
from authlib.integrations.flask_client import OAuth
import os
import time
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from dotenv import load_dotenv
import sys
from datetime import datetime


sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


from my_app.azure.azure_blob_storage import AzureBlobStorage
from my_app.fantasy_platforms_integration.yahoo.sync_yahoo_league import YahooLeague

env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path) # Loads from .env or .env.vault if DOTENV_KEY is set

# Create the main Flask app
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
YAHOO_REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URL")

# Google OAuth Config
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Authlib setup for both Yahoo and Google
oauth = OAuth(app)
supaBase_manager = YahooAuthManager()
# Yahoo OAuth
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

# Google OAuth
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),    
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url=GOOGLE_DISCOVERY_URL,
    client_kwargs={
        'scope': 'openid email profile'
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

# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.route('/')
def homepage():
    """Main homepage with links to different services"""
    return '''
    <h1>Fantasy League App</h1>
    <p>Choose your authentication method:</p>
    <ul>
        <li><a href="/yahoo/login">Login with Yahoo</a></li>
        <li><a href="/google/login">Login with Google</a></li>
        <li><a href="/sync_league">Sync League (Debug)</a></li>
        <li><a href="/health">Health Check</a></li>
    </ul>
    '''

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Fantasy League App",
        "timestamp": time.time()
    })

# ============================================================================
# YAHOO OAUTH ROUTES
# ============================================================================

@app.route('/yahoo/login')
def yahoo_login():
    """Yahoo OAuth login"""
    if DEBUG:
        return redirect('/yahoo/debug_league')
    return yahoo.authorize_redirect(redirect_uri=YAHOO_REDIRECT_URI + "/yahoo/callback")

@app.route('/yahoo/callback')
def yahoo_callback():
    """Yahoo OAuth callback"""
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
    <form action="/yahoo/select_league" method="post">
        {% for league in leagues %}
            <input type="radio" name="league_id" value="{{ league.id }}" required> {{ league.name }}<br>
        {% endfor %}
        <button type="submit">Continue</button>
    </form>
    '''
    return render_template_string(html, leagues=league_options)

@app.route('/yahoo/select_league', methods=['POST'])
def yahoo_select_league():
    """Handle league selection"""
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

    return f"You synced: {results}"

@app.route('/yahoo/debug_league')
def yahoo_debug_league():
    """Debug endpoint for league sync"""
    sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    league = yahoo_game.to_league('428.l.41083')
    yahoo_league = YahooLeague(league)
    results = yahoo_league.sync_full_league()
    return f"You synced: {results}"

@app.route('/sync_league')
def sync_league():
    """Direct sync endpoint"""
    try:
        sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
        yahoo_game = yfa.Game(sc, 'nba')
        league = yahoo_game.to_league('428.l.41083')
        yahoo_league = YahooLeague(league)
        results = yahoo_league.sync_full_league()
        return jsonify({
            "message": "League sync completed",
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# GOOGLE OAUTH ROUTES
# ============================================================================

@app.route('/google/login')
def google_login():
    """Google OAuth login"""
    google = oauth.create_client('google') 
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    scheme = 'https' if not app.debug else 'http'
    redirect_uri = url_for('google_callback', _external=True, _scheme=scheme)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def google_callback():
    """Google OAuth callback"""
    google = oauth.create_client('google')
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    token = google.authorize_access_token()
    resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
    user_info = resp.json()
    session['google_user'] = user_info
    google_user_id = user_info['sub']
    full_name = user_info['name']
    email = user_info['email']
 
    return f"Hello, {user_info['email']}! <a href='/logout'>Logout</a>"

# ============================================================================
# UTILITY ROUTES
# ============================================================================

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect('/')

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

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
