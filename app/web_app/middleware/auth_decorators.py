from functools import wraps
from flask import redirect, url_for, session

def require_google_auth(f):
    """Decorator to require Google authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'google_user' not in session:
            return redirect(url_for('google_login'))
        return f(*args, **kwargs)
    return decorated_function
