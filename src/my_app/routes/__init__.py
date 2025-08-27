from .main_routes import main_bp
from .auth_routes import auth_bp
from .yahoo_routes import yahoo_bp
from .api_routes import api_bp

def register_routes(app):
    """Register all route blueprints with the Flask app"""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(yahoo_bp)
    app.register_blueprint(api_bp)
