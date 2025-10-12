from config.dependencies import (
    openai_agent_manager,
    openai_file_manager,
)
from router.auth_routes import AuthRouter
from router.main_routes import MainRouter
from router.yahoo_routes import YahooRouter
from router.openai_agent_router import OpenaiAgentRouter
from router.openai_file_router import OpenaiFilesRouter


def register_routes(app):
    """Register all route blueprints with the Flask app"""
    # Create router instances with dependencies
    main_router = MainRouter(openai_file_manager())
    auth_router = AuthRouter(openai_file_manager())
    yahoo_router = YahooRouter(openai_file_manager())
    openai_agent_router = OpenaiAgentRouter(openai_agent_manager())
    openai_file_router = OpenaiFilesRouter(openai_file_manager())
    
    # Register blueprints
    app.register_blueprint(main_router.get_bp())
    app.register_blueprint(auth_router.get_bp())
    app.register_blueprint(yahoo_router.get_bp())
    app.register_blueprint(openai_agent_router.get_bp())
    app.register_blueprint(openai_file_router.get_bp())
