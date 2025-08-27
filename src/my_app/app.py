from flask import Flask
from my_app.config.settings import configure_app
from my_app.config.oauth_config import configure_oauth
from my_app.routes import register_routes
import os

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configure app settings
    configure_app(app)
    
    # Configure OAuth
    oauth = configure_oauth(app)
    app.oauth = oauth  # Store oauth instance in app for routes to access
    
    # Register all routes
    register_routes(app)
    
    return app

# Create the app instance
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
