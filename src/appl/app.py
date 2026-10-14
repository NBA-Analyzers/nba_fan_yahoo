from flask import Flask, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from appl.fantasy_integrations.yahoo.sync_league.yahoo_tokens import load_saved_entry
from appl.config.dependencies import set_services
from appl.config.app_config import configure_app
from appl.config.oauth_config import configure_oauth
from appl.router import register_routes
import logging
import os

# Gunicorn doesn't configure the root logger, so without this INFO logs (sync results,
# skipped re-indexes) never reach Cloud Logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app():
    # Serve static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path="/static",
        template_folder=static_dir,
    )

    # Configure app to work behind ngrok proxy (HTTPS)
    app.config["PREFERRED_URL_SCHEME"] = "https"

    # Trust proxy headers from ngrok
    app.config["SERVER_NAME"] = None

    # Apply ProxyFix middleware to handle ngrok headers properly
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)

    # Middleware to handle ngrok proxy headers
    @app.before_request
    def before_request():
        # Check if we're behind ngrok and force HTTPS
        if request.headers.get("X-Forwarded-Proto") == "https":
            request.environ["wsgi.url_scheme"] = "https"

    @app.before_request
    def restore_yahoo_connection():
        # Bring back the saved Yahoo connection after a logout or in a new browser,
        # instead of sending the user through "Connect Yahoo" again. Checked once per session.
        if request.endpoint == "static" or "user_id" not in session:
            return
        if session.get("yahoo_restore_checked") or session.get("user") in session.get("token_store", {}):
            return
        session["yahoo_restore_checked"] = True
        try:
            entry = load_saved_entry(session["user_id"])
        except Exception as e:
            logging.getLogger(__name__).warning(f"Could not restore Yahoo connection: {e}")
            return
        if entry:
            session.setdefault("token_store", {})[entry["guid"]] = entry
            session["user"] = entry["guid"]
            session.modified = True

    # Configure app settings
    configure_app(app)

    # Configure OAuth
    oauth = configure_oauth(app)
    app.oauth = oauth  # Store oauth instance in app for routes to access


    set_services()

    # Register all routes
    register_routes(app)

    return app


# Create the app instance
app = create_app()

if __name__ == "__main__":
    # The auto-reloader restarts the server on every .py change (including tests); opt in with RELOAD=true
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        debug=True,
        use_reloader=os.environ.get("RELOAD", "").lower() == "true",
    )
