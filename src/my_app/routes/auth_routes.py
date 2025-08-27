from flask import Blueprint, session, redirect, url_for, request
from ..middleware.auth_decorators import require_google_auth
from ..supaBase.models.yahoo_auth import YahooAuth
from ..supaBase.models.google_auth import GoogleAuth
from ..supaBase.models.google_fantasy import GoogleFantasy
from ..supaBase.services.auth_services import AuthService
from ..supaBase.services.fantasy_services import FantasyService
from ..supaBase.exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError
from ..config.settings import DEBUG
import time
import xml.etree.ElementTree as ET

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/google/login')
def google_login():
    """Google OAuth login - First step in authentication flow"""
    from flask import current_app
    google = current_app.oauth.create_client('google') 
    if google is None:
        print("ERROR: Google OAuth client is not available!")
        return "Google OAuth client not configured", 500
    scheme = 'https' if not current_app.debug else 'http'
    redirect_uri = url_for('auth.google_callback', _external=True, _scheme=scheme)
    return google.authorize_redirect(redirect_uri)

@auth_bp.route('/google/callback')
def google_callback():
    """Google OAuth callback - After successful Google auth, redirect to dashboard"""
    from flask import current_app
    google = current_app.oauth.create_client('google')
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
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        print(f"❌ Error during Google callback: {e}")
        return "Google login failed. Please try again.", 500

@auth_bp.route('/yahoo/login')
@require_google_auth
def yahoo_login():
    """Yahoo OAuth login - Requires Google authentication first"""
    if DEBUG:
        return redirect('/yahoo/debug_league')
    
    from flask import current_app
    yahoo = current_app.oauth.create_client('yahoo')
    return yahoo.authorize_redirect(redirect_uri=current_app.config.get('YAHOO_REDIRECT_URI') + "/auth/yahoo/callback")

@auth_bp.route('/yahoo/callback')
@require_google_auth
def yahoo_callback():
    """Yahoo OAuth callback - Requires Google authentication first"""
    try:
        from flask import current_app
        yahoo = current_app.oauth.create_client('yahoo')
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

        # Initialize token store in session if it doesn't exist
        if 'token_store' not in session:
            session['token_store'] = {}
            
        # Store tokens in session and token store
        session['token_store'][user_guid] = {
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

        google_user_info = session.get('google_user', {})
        google_user_id = google_user_info.get('sub')
        
        if google_user_id:
            try:
                # Create the fantasy connection
                google_fantasy = GoogleFantasy(
                    google_user_id=google_user_id,
                    fantasy_user_id=user_guid,  # This is the Yahoo user ID
                    fantasy_platform='yahoo'
                )
                
                # Use FantasyService to create the connection
                fantasy_service = FantasyService()
                fantasy_connection = fantasy_service.connect_fantasy_platform(google_fantasy)
                
                print(f"✅ Fantasy connection created successfully!")
                print(f"   Google User: {fantasy_connection.google_user_id}")
                print(f"   Yahoo User: {fantasy_connection.fantasy_user_id}")
                print(f"   Platform: {fantasy_connection.fantasy_platform}")
                
                # Store connection info in session for reference
                session['fantasy_connected'] = True
                session['fantasy_connection_created_at'] = fantasy_connection.created_at
                
            except DuplicateError as e:
                print(f"⚠️  Fantasy connection already exists: {str(e)}")
                session['fantasy_connected'] = True
                # This is not an error - connection already exists
                
            except ValidationError as e:
                print(f"❌ Fantasy connection validation error: {str(e)}")
                # Continue with the flow even if connection fails
                
            except Exception as e:
                print(f"❌ Unexpected error creating fantasy connection: {str(e)}")
                # Continue with the flow even if connection fails
        else:
            print("❌ Could not find Google user ID in session for fantasy connection")

        # Get leagues for selection
        from my_app.services.yahoo_service import YahooService
        yahoo_service = YahooService(session['token_store'])
        league_options = yahoo_service.get_user_leagues(user_guid)

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
        return html
        
    except Exception as e:
        print(f"❌ Error during Yahoo callback: {e}")
        return "Yahoo login failed. Please try again.", 500

@auth_bp.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect('/')
