# Yahoo Fantasy OAuth Multi-User Flow (Flask + Authlib)

from flask import Flask, redirect, request, session, url_for
from authlib.integrations.flask_client import OAuth
import os
import time

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")  # secure in prod

# Configuration (replace with your Yahoo app info)
YAHOO_CLIENT_ID = "dj0yJmk9Vmx3STVwNzVnNFVOJmQ9WVdrOU9UbDFabFU1V1dZbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTUw"
YAHOO_CLIENT_SECRET = "c6ecb8500877349e193025923afce04baf6fd315"
REDIRECT_URI = "localhost:5000/callback"

# Authlib setup
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

# In-memory token store (for demo)
token_store = {}

@app.route('/')
def homepage():
    return '<a href="/login">Login with Yahoo</a>'

@app.route('/login')
def login():
    return yahoo.authorize_redirect(redirect_uri=REDIRECT_URI)

@app.route('/callback')
def callback():
    token = yahoo.authorize_access_token()
    user_guid = token['xoauth_yahoo_guid']
    # Save token per user (in real use, save in DB)
    token_store[user_guid] = {
        'access_token': token['access_token'],
        'refresh_token': token['refresh_token'],
        'expires_at': time.time() + token['expires_in'],
        'guid': user_guid
    }
    session['user'] = user_guid
    return redirect('/leagues')

@app.route('/leagues')
def leagues():
    user_guid = session.get('user')
    if not user_guid or user_guid not in token_store:
        return redirect('/')

    token_data = token_store[user_guid]
    resp = yahoo.get(
        f"fantasy/v2/users;use_login=1/games;game_keys=nba/leagues",
        token=token_data['access_token']
    )
    return resp.text

if __name__ == '__main__':
    app.run(debug=True)
