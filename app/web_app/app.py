from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from config.dependencies import set_services


from config.app_config import configure_app
from config.oauth_config import configure_oauth
from router import register_routes
import os


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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
