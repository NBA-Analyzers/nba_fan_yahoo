from flask import Blueprint, session, redirect, url_for, jsonify
import time

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def homepage():
    """Main homepage with login options"""
    # Check if user is already logged in with Google
    if 'google_user' in session:
        return redirect(url_for('main.dashboard'))
    
    # Show homepage with login options
    return '''
    <h1>Fantasy League App</h1>
    <p>Welcome! Please login to get started:</p>
    <ul>
        <li><a href="/auth/google/login">Login with Google</a></li>
    </ul>
    <hr>
    <p>Other options:</p>
    <ul>
        <li><a href="/api/sync_league">Sync League (Debug)</a></li>
        <li><a href="/health">Health Check</a></li>
    </ul>
    '''

@main_bp.route('/dashboard')
def dashboard():
    """Dashboard page after Google authentication - shows Yahoo login option"""
    from ..middleware.auth_decorators import require_google_auth
    
    @require_google_auth
    def dashboard_content():
        user_info = session.get('google_user', {})
        user_name = user_info.get('name', 'User')
        
        # Check if user also has Yahoo authentication
        yahoo_authenticated = 'user' in session and session['user'] in session.get('token_store', {})
        
        html = f'''
        <h1>Welcome, {user_name}!</h1>
        <p>You are logged in with Google.</p>
        
        <h2>Connect to Yahoo Fantasy</h2>
        <p>To access your fantasy leagues, please connect your Yahoo account:</p>
        
        {'<p>✅ Yahoo account connected!</p>' if yahoo_authenticated else ''}
        
        <ul>
            <li><a href="/auth/yahoo/login">{'Re-connect' if yahoo_authenticated else 'Connect'} Yahoo Account</a></li>
            {'<li><a href="/yahoo/my_leagues">View My Synced Leagues</a></li>' if yahoo_authenticated else ''}
            <li><a href="/api/sync_league">Sync League (Debug)</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/auth/logout">Logout</a></li>
        </ul>
        '''
        
        return html
    
    return dashboard_content()

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Fantasy League App",
        "timestamp": time.time()
    })
