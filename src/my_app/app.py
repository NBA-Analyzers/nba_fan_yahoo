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

# Import our database models and services
from my_app.supaBase.models.yahoo_auth import YahooAuth
from my_app.supaBase.models.google_auth import GoogleAuth
# from my_app.supaBase.models.google_fantasy import GoogleFantasy
from my_app.supaBase.services.auth_services import AuthService
# from my_app.supaBase.services.fantasy_services import FantasyService
# from my_app.supaBase.exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

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

def require_google_auth(f):
    """Decorator to require Google authentication"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'google_user' not in session:
            return redirect(url_for('google_login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.route('/')
def homepage():
    """Main homepage with login options"""
    # Check if user is already logged in with Google
    if 'google_user' in session:
        return redirect(url_for('dashboard'))
    
    # Show homepage with login options
    return '''
    <h1>Fantasy League App</h1>
    <p>Welcome! Please login to get started:</p>
    <ul>
        <li><a href="/google/login">Login with Google</a></li>
    </ul>
    <hr>
    <p>Other options:</p>
    <ul>
        <li><a href="/sync_league">Sync League (Debug)</a></li>
        <li><a href="/health">Health Check</a></li>
    </ul>
    '''

@app.route('/dashboard')
@require_google_auth
def dashboard():
    """Dashboard page after Google authentication - shows Yahoo login option"""
    user_info = session.get('google_user', {})
    user_name = user_info.get('name', 'User')
    
    # Check if user also has Yahoo authentication
    yahoo_authenticated = 'user' in session and session['user'] in token_store
    
    html = f'''
    <h1>Welcome, {user_name}!</h1>
    <p>You are logged in with Google.</p>
    
    <h2>Connect to Yahoo Fantasy</h2>
    <p>To access your fantasy leagues, please connect your Yahoo account:</p>
    
    {'<p>✅ Yahoo account connected!</p>' if yahoo_authenticated else ''}
    
    <ul>
        <li><a href="/yahoo/login">{'Re-connect' if yahoo_authenticated else 'Connect'} Yahoo Account</a></li>
        <li><a href="/sync_league">Sync League (Debug)</a></li>
        <li><a href="/health">Health Check</a></li>
        <li><a href="/logout">Logout</a></li>
    </ul>
    '''
    
    return html

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Fantasy League App",
        "timestamp": time.time()
    })

# ============================================================================
# GOOGLE OAUTH ROUTES (First Step)
# ============================================================================

@app.route('/google/login')
def google_login():
    """Google OAuth login - First step in authentication flow"""
    google = oauth.create_client('google') 
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    scheme = 'https' if not app.debug else 'http'
    redirect_uri = url_for('google_callback', _external=True, _scheme=scheme)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def google_callback():
    """Google OAuth callback - After successful Google auth, redirect to dashboard"""
    google = oauth.create_client('google')
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    
    try:
        token = google.authorize_access_token()
        resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
        user_info = resp.json()
        
        # Store user info in session
        session['google_user'] = user_info
        
        # Extract user data
        google_user_id = user_info['sub']
        full_name = user_info['name']
        email = user_info['email']
        access_token = token['access_token']
        
        # Create GoogleAuth object
        google_auth = GoogleAuth(
            google_user_id=google_user_id,
            full_name=full_name,
            email=email,
            access_token=access_token
        )
        
        # Insert or update user in database using AuthService
        auth_service = AuthService()
        try:
            created_user = auth_service.create_or_update_google_user(google_auth)
            print(f"✅ User successfully saved to database: {created_user.full_name}")
        except Exception as e:
            print(f"❌ Database operation failed: {e}")
            # Continue with login even if database fails
        
        # Redirect to dashboard instead of showing user info directly
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        print(f"❌ Error during Google callback: {e}")
        return "Google login failed. Please try again.", 500

# ============================================================================
# YAHOO OAUTH ROUTES (Second Step)
# ============================================================================

@app.route('/yahoo/login')
@require_google_auth
def yahoo_login():
    """Yahoo OAuth login - Requires Google authentication first"""
    if DEBUG:
        return redirect('/yahoo/debug_league')
    return yahoo.authorize_redirect(redirect_uri=YAHOO_REDIRECT_URI + "/yahoo/callback")

@app.route('/yahoo/callback')
@require_google_auth
def yahoo_callback():
    """Yahoo OAuth callback - Requires Google authentication first"""
    try:
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

        # Store tokens in session and token store
        token_store[user_guid] = {
            'access_token': token['access_token'],
            'refresh_token': token['refresh_token'],
            'expires_at': time.time() + token['expires_in'],
            'guid': user_guid
        }

        session['user'] = user_guid

        # Create YahooAuth object for database insertion
        yahoo_auth = YahooAuth(
            yahoo_user_id=user_guid,
            access_token=token['access_token'],
            refresh_token=token['refresh_token']
        )
        
        # Insert or update user in database using AuthService
        auth_service = AuthService()
        try:
            created_user = auth_service.create_or_update_yahoo_user(yahoo_auth)
            print(f"✅ Yahoo user successfully saved to database: {created_user.yahoo_user_id}")
        except Exception as e:
            print(f"❌ Database operation failed: {e}")
            # Continue with login even if database fails

        sc = CustomYahooSession(token_store[user_guid])
        yahoo_game = yfa.Game(sc, 'nba')

        yahoo_game = get_yahoo_sdk()
        
        league_ids = yahoo_game.league_ids()
        league_options = []
        for league_id in league_ids:
            league = yahoo_game.to_league(league_id)
            league_name = league.settings()['name']
            league_options.append({'id': league_id, 'name': league_name})

        # Get Google user info for personalization
        user_info = session.get('google_user', {})
        user_name = user_info.get('name', 'User')

        # Render a simple HTML form for league selection
        html = f'''
        <h2>Hello {user_name}!</h2>
        <h3>Your Yahoo Fantasy Leagues</h3>
        <p>Yahoo account connected successfully! Select your league:</p>
        <form action="/yahoo/select_league" method="post">
            {{% for league in leagues %}}
                <input type="radio" name="league_id" value="{{{{ league.id }}}}" required> {{{{ league.name }}}}<br>
            {{% endfor %}}
            <br>
            <button type="submit">Sync This League</button>
        </form>
        <br>
        <a href="/dashboard">← Back to Dashboard</a>
        '''
        return render_template_string(html, leagues=league_options)
        
    except Exception as e:
        print(f"❌ Error during Yahoo callback: {e}")
        return "Yahoo login failed. Please try again.", 500

@app.route('/yahoo/select_league', methods=['POST'])
@require_google_auth
def yahoo_select_league():
    """Handle league selection - Requires Google authentication first"""
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

    return f"<h2>League Sync Complete!</h2><p>Results: {results}</p><br><a href='/dashboard'>← Back to Dashboard</a>"

@app.route('/yahoo/debug_league')
@require_google_auth
def yahoo_debug_league():
    """Debug endpoint for league sync - Requires Google authentication first"""
    sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    league = yahoo_game.to_league('428.l.41083')
    yahoo_league = YahooLeague(league)
    results = yahoo_league.sync_full_league()
    return f"<h2>Debug League Sync Complete!</h2><p>Results: {results}</p><br><a href='/dashboard'>← Back to Dashboard</a>"

@app.route('/sync_league')
@require_google_auth
def sync_league():
    """Direct sync endpoint - Requires Google authentication first"""
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
# UTILITY ROUTES
# ============================================================================

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    token_store.clear()  # Also clear the token store
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
