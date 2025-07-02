from flask import Flask, redirect, url_for, session, request
from authlib.integrations.flask_client import OAuth
import os

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
    google =oauth.create_client('google') 
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
    token = google.authorize_access_token()
    resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
    user_info = resp.json()
    session['google_user'] = user_info
    return f"Hello, {user_info['email']}! <a href='/logout'>Logout</a>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/')
def homepage():
    return '''
        <a href="/google/login">Sign in with Google</a>
    '''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', use_reloader=False, port=5002) 