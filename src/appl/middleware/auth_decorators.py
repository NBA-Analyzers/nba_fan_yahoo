from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def _wants_json() -> bool:
    """API calls (a JSON body, or an explicit JSON Accept) get a status code; a browser
    page load or form post is redirected to the sign-in page."""
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["text/html", "application/json"])
    return best == "application/json"


def require_login(f):
    """Decorator to require a signed-in user (any login provider)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if _wants_json():
                return jsonify({"error": "Please sign in first"}), 401
            return redirect(url_for('main.homepage'))
        return f(*args, **kwargs)
    return decorated_function
