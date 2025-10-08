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
        
        # Get user's synced leagues if they have Yahoo auth
        synced_leagues_html = ""
        if yahoo_authenticated:
            try:
                from ..services.yahoo_service import YahooService
                yahoo_service = YahooService(session['token_store'])
                user_leagues = yahoo_service.get_user_synced_leagues(session['user'])
                
                if user_leagues:
                    # Build league HTML dynamically
                    league_items = []
                    for league in user_leagues:
                        league_items.append(f'''
                        <div style="border: 1px solid #dee2e6; padding: 15px; margin: 10px 0; border-radius: 8px; background: white;">
                            <h4>League: {league.get('league_id', 'Unknown')}</h4>
                            <p><strong>Team:</strong> {league.get('team_name', 'Unknown Team')}</p>
                            <p><strong>Added:</strong> {league.get('created_at', 'Unknown')}</p>
                            <a href="/ai-chat/{league.get('league_id', 'unknown')}" style="background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-size: 14px;">AI Chat</a>
                        </div>
                        ''')
                    
                    synced_leagues_html = f'''
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3>Your Synced Leagues</h3>
                        <p>Click on any league to access its AI Assistant:</p>
                        {''.join(league_items)}
                    </div>
                    '''
                else:
                    synced_leagues_html = '''
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3>Your Synced Leagues</h3>
                        <p>No leagues synced yet. Connect your Yahoo account to get started!</p>
                    </div>
                    '''
            except Exception as e:
                print(f"Error getting synced leagues: {e}")
                synced_leagues_html = '''
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Your Synced Leagues</h3>
                    <p>Error loading leagues. Please try refreshing the page.</p>
                </div>
                '''
        
        html = f'''
        <h1>Welcome, {user_name}!</h1>
        <p>You are logged in with Google.</p>
        
        <h2>Connect to Yahoo Fantasy</h2>
        <p>To access your fantasy leagues, please connect your Yahoo account:</p>
        
        {'<p>Yahoo account connected!</p>' if yahoo_authenticated else ''}
        
        <ul>
            <li>
                <a href="/auth/yahoo/login" id="yahooLoginLink" onclick="showYahooLoading()">
                    <span id="yahooLoginText">{'Re-connect' if yahoo_authenticated else 'Connect'} Yahoo Account</span>
                    <span id="yahooLoadingSpinner" style="display: none;">⏳ Connecting...</span>
                </a>
            </li>
            {'<li><a href="/yahoo/my_leagues">View My Synced Leagues</a></li>' if yahoo_authenticated else ''}
            <li><a href="/api/sync_league">Sync League (Debug)</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/auth/logout">Logout</a></li>
        </ul>
        
        {synced_leagues_html}
        
        <script>
        function showYahooLoading() {{
            // Show loading spinner and hide original text
            document.getElementById('yahooLoginText').style.display = 'none';
            document.getElementById('yahooLoadingSpinner').style.display = 'inline';
            
            // Optional: Add a timeout to re-enable if something goes wrong
            setTimeout(function() {{
                document.getElementById('yahooLoginText').style.display = 'inline';
                document.getElementById('yahooLoadingSpinner').style.display = 'none';
            }}, 30000); // 30 second timeout
        }}
        </script>
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

@main_bp.route('/ai-chat/<league_id>')
def ai_chat(league_id):
    """AI Chat interface for a specific league - placeholder for future AI integration"""
    from ..middleware.auth_decorators import require_google_auth
    
    @require_google_auth
    def chat_content():
        user_info = session.get('google_user', {})
        user_name = user_info.get('name', 'User')
        
        # Get user's connected Yahoo info
        yahoo_authenticated = 'user' in session and session['user'] in session.get('token_store', {})
        
        if not yahoo_authenticated:
            return redirect(url_for('main.dashboard'))
        
        html = f'''
        <h1>Fantasy AI Assistant</h1>
        <p>Welcome, {user_name}!</p>
        
        <div style="background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h2>🎯 Your Connected League</h2>
            <p><strong>League ID:</strong> {league_id}</p>
            <p>✅ Yahoo Fantasy League Connected</p>
            <p>✅ Team Data Synced</p>
            <p>✅ Ready for AI Analysis</p>
        </div>
        
        <div style="background: #e8f4fd; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h2>🤖 AI Chat Interface</h2>
            <p><em>This is where your AI chat will be implemented for league {league_id}!</em></p>
            <p>Users will be able to ask questions like:</p>
            <ul>
                <li>"How is my team performing this week in this league?"</li>
                <li>"Who should I pick up from free agents in this league?"</li>
                <li>"How do I match up against my opponent this week?"</li>
                <li>"Should I make this trade for my team?"</li>
            </ul>
        </div>
        
        <div style="margin: 20px 0;">
            <a href="/dashboard" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a>
            <a href="/auth/logout" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-left: 10px;">Logout</a>
        </div>
        '''
        
        return html
    
    return chat_content()
