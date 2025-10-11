from flask import Flask, redirect, request, session, url_for, jsonify, render_template_string
from authlib.integrations.flask_client import OAuth
import os
import time
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from dotenv import load_dotenv

from ..repository.azure.azure_blob_storage import AzureBlobStorage

# Add the supaBase directory to the path for imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'supaBase'))

# Import our database models and services
from ..repository.supaBase.models.yahoo_auth import YahooAuth
from ..repository.supaBase.models.google_fantasy import GoogleFantasy
from ..repository.supaBase.services.auth_services import AuthService
from ..repository.supaBase.services.fantasy_services import FantasyService
from ..repository.supaBase.exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Go up to the project root (nba_fan_yahoo directory)
project_root = os.path.join(script_dir, "..", "..")
# Load .env from the project root
env_path = os.path.join(project_root, ".env")
load_dotenv(env_path)


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
YAHOO_REDIRECT_URL = os.getenv("YAHOO_REDIRECT_URL")

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
    return '''
        <h1>Yahoo Fantasy Sports Integration</h1>
        <p><a href="/login">Login with Yahoo</a></p>
        <p><a href="/connect_yahoo_to_google">Connect Yahoo Account to Google</a></p>
        <p><a href="/view_connections">View Fantasy Connections</a></p>
        <p><a href="/debug_league">Debug League Sync</a></p>
    '''

@app.route('/login')
def login():
    
    """Start Yahoo OAuth with debugging"""
    redirect_uri = YAHOO_REDIRECT_URL + "/yahoo/callback"
    
    print("=== YAHOO LOGIN DEBUG ===")
    print(f"Generated redirect URI: {redirect_uri}")
    print(f"Client ID: {YAHOO_CLIENT_ID}")
    print(f"Using scope: openid")
    
    try:
        # Try to get the authorization URL
        return yahoo.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"Error in authorize_redirect: {e}")
        return f'''
        <h2>OAuth Error</h2>
        <p>Error: {str(e)}</p>
        <p>Check console for details.</p>
        <a href="/debug-oauth">View Debug Info</a>
        '''

@app.route('/callback')
def callback():
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

        # Create a Google Fantasy connection entry for this Yahoo user
        # This allows the Yahoo user to be linked to Google users later
        fantasy_service = FantasyService()
        try:
            # Note: We don't create a GoogleFantasy entry yet because we need a google_user_id
            # Instead, we'll create it when a Google user connects their Yahoo account
            print(f"✅ Yahoo user {user_guid} successfully authenticated")
            print(f"   - This user can now be linked to Google accounts through the connection process")
            
        except Exception as e:
            print(f"⚠️ Fantasy connection setup note: {e}")
            # This is not critical, so we continue

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
        <p><strong>Your Yahoo User ID:</strong> <code>{user_guid}</code></p>
        <p><small>Save this ID to connect your Yahoo account to Google later</small></p>
        <form action="/select_league" method="post">
            {% for league in leagues %}
                <input type="radio" name="league_id" value="{{ league.id }}" required> {{ league.name }}<br>
            {% endfor %}
            <button type="submit">Continue</button>
        </form>
        <p><a href="/connect_yahoo_to_google">Connect to Google Account</a></p>
        '''
        return render_template_string(html, leagues=league_options, user_guid=user_guid)
        
    except Exception as e:
        print(f"❌ Error during Yahoo callback: {e}")
        return "Login failed. Please try again.", 500

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

    return f"You synced: {results}" # Display the selected league name

@app.route('/connect_yahoo_to_google', methods=['GET', 'POST'])
def connect_yahoo_to_google():
    """Route for Google users to connect their Yahoo accounts"""
    if request.method == 'GET':
        # Show the connection form
        return '''
        <h2>Connect Your Yahoo Account to Google</h2>
        <form method="POST">
            <label for="google_user_id">Google User ID:</label><br>
            <input type="text" id="google_user_id" name="google_user_id" required><br><br>
            
            <label for="yahoo_user_id">Yahoo User ID (GUID):</label><br>
            <input type="text" id="yahoo_user_id" name="yahoo_user_id" required><br><br>
            
            <button type="submit">Connect Accounts</button>
        </form>
        <p><small>Note: You need to have logged in with both Google and Yahoo first</small></p>
        '''
    
    elif request.method == 'POST':
        try:
            google_user_id = request.form['google_user_id']
            yahoo_user_id = request.form['yahoo_user_id']
            
            # Validate that both users exist
            auth_service = AuthService()
            fantasy_service = FantasyService()
            
            # Check if Google user exists
            google_user = auth_service.get_google_user(google_user_id)
            if not google_user:
                return f"❌ Google user with ID {google_user_id} not found. Please log in with Google first.", 400
            
            # Check if Yahoo user exists
            yahoo_user = auth_service.get_yahoo_user(yahoo_user_id)
            if not yahoo_user:
                return f"❌ Yahoo user with ID {yahoo_user_id} not found. Please log in with Yahoo first.", 400
            
            # Create the Google Fantasy connection
            google_fantasy = GoogleFantasy(
                google_user_id=google_user_id,
                fantasy_user_id=yahoo_user_id,
                fantasy_platform="yahoo"
            )
            
            # Connect the accounts
            created_connection = fantasy_service.connect_fantasy_platform(google_fantasy)
            
            return f'''
            <h2>✅ Accounts Successfully Connected!</h2>
            <p>Google user <strong>{google_user.full_name}</strong> is now connected to Yahoo user <strong>{yahoo_user_id}</strong></p>
            <p><a href="/">Return to Home</a></p>
            '''
            
        except ValidationError as e:
            return f"❌ Validation error: {e}", 400
        except NotFoundError as e:
            return f"❌ Not found error: {e}", 400
        except DuplicateError as e:
            return f"❌ Duplicate error: {e}", 400
        except Exception as e:
            return f"❌ Unexpected error: {e}", 500

@app.route('/view_connections')
def view_connections():
    """Route to view existing fantasy connections"""
    try:
        fantasy_service = FantasyService()
        
        # Get all connections (this would need to be implemented in the service)
        # For now, we'll show a message about the feature
        return '''
        <h2>Fantasy Connections</h2>
        <p>This feature will show all existing connections between Google and Yahoo users.</p>
        <p><strong>Note:</strong> The view connections functionality is being implemented.</p>
        <p><a href="/">Return to Home</a></p>
        '''
        
    except Exception as e:
        return f"❌ Error viewing connections: {e}", 500

@app.route('/debug_league')
def debug_league():
    sc = OAuth2(None, None, from_file='src/my_app/fantasy_platforms_integration/yahoo/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    league = yahoo_game.to_league('428.l.41083')
    yahoo_league = YahooLeague(league)
    results = yahoo_league.sync_full_league()
    return f"You synced: {results}" # Display the selected league name

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
    print("✓ App will run on https://localhost:5001")
    print("✓ Debug mode: ON")
    app.run(debug=True, host='0.0.0.0',  port=5001,ssl_context='adhoc')
