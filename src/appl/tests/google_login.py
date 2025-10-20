from flask import Flask, redirect, url_for, session, request
from authlib.integrations.flask_client import OAuth
import os
import sys
from dotenv import load_dotenv

# Ensure the 'supaBase' package (located under src/appl/tests) is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src', 'appl','tests')))

# Import our database models and services
from ..repository.supaBase.models.google_auth import GoogleAuth
from ..repository.supaBase.models.google_fantasy import GoogleFantasy
from ..repository.supaBase.services.auth_services import AuthService
from ..repository.supaBase.services.fantasy_services import FantasyService
from ..repository.supaBase.exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(env_path) # Loads from .env or .env.vault if DOTENV_KEY is set

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")

# --- Google OAuth Config ---
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),    
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url=GOOGLE_DISCOVERY_URL,
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@app.route('/google/login')
def google_login():
    google = oauth.create_client('google') 
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def google_callback():
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
        
        # Show user their Google user ID for easy reference
        return f'''
        <h2>✅ Welcome, {user_info['email']}!</h2>
        <p><strong>Your Google User ID:</strong> <code>{google_user_id}</code></p>
        <p><small>Save this ID to connect your Google account to Yahoo later</small></p>
        <p><a href="/connect_yahoo_to_google">Connect to Yahoo Account</a></p>
        <p><a href="/logout">Logout</a></p>
        '''
        
    except Exception as e:
        print(f"❌ Error during Google callback: {e}")
        return "Login failed. Please try again.", 500

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/')
def homepage():
    return '''
        <h1>Google OAuth Integration</h1>
        <p><a href="/google/login">Sign in with Google</a></p>
        <p><a href="/connect_yahoo_to_google">Connect Yahoo Account to Google</a></p>
        <p><small>Note: You need to have logged in with both Google and Yahoo first to connect accounts</small></p>
    '''

if __name__ == '__main__':
    app.run(debug=True, host='localhost', use_reloader=False, port=5001)