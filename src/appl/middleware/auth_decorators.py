from functools import wraps
from flask import redirect, url_for, session

def require_login(f):
    """Decorator to require a signed-in user (any login provider)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.homepage'))
        return f(*args, **kwargs)
    return decorated_function
