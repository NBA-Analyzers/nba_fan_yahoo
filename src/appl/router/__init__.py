from ..config.dependencies import (
    chat_service,
    document_indexer,
)
from ..ai.access import SessionAccess
from ..ai.chat_router import ChatRouter
from ..repository.supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
from .auth_routes import AuthRouter
from .main_routes import MainRouter
from .yahoo_routes import YahooRouter
from .document_router import DocumentRouter


def register_routes(app):
    """Register all route blueprints with the Flask app"""
    # Create router instances with dependencies
    main_router = MainRouter(document_indexer())
    auth_router = AuthRouter(document_indexer())
    yahoo_router = YahooRouter(document_indexer())
    chat_router = ChatRouter(chat_service(), SessionAccess(YahooLeagueRepository))
    document_router = DocumentRouter(document_indexer())

    # Register blueprints
    app.register_blueprint(main_router.get_bp())
    app.register_blueprint(auth_router.get_bp())
    app.register_blueprint(yahoo_router.get_bp())
    app.register_blueprint(chat_router.get_bp())
    app.register_blueprint(document_router.get_bp())
