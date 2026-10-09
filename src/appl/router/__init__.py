from ..config.dependencies import (
    chat_service,
    document_indexer,
)
from ..ai.access import SessionAccess
from ..draft.manual_league import default_store
from ..ai.chat_router import ChatRouter
from ..repository.supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
from .auth_routes import AuthRouter
from .draft_routes import DraftRouter
from .main_routes import MainRouter
from .season_routes import SeasonRouter
from .yahoo_routes import YahooRouter
from .document_router import DocumentRouter


def register_routes(app):
    """Register all route blueprints with the Flask app"""
    # Create router instances with dependencies
    manual_store = default_store()
    main_router = MainRouter(document_indexer(), manual_store)
    auth_router = AuthRouter(document_indexer())
    yahoo_router = YahooRouter(document_indexer())
    chat_router = ChatRouter(chat_service(), SessionAccess(YahooLeagueRepository, manual_store))
    document_router = DocumentRouter(document_indexer())
    draft_router = DraftRouter(manual_store)
    season_router = SeasonRouter(manual_store)

    # Register blueprints
    app.register_blueprint(main_router.get_bp())
    app.register_blueprint(auth_router.get_bp())
    app.register_blueprint(yahoo_router.get_bp())
    app.register_blueprint(chat_router.get_bp())
    app.register_blueprint(document_router.get_bp())
    app.register_blueprint(draft_router.get_bp())
    app.register_blueprint(draft_router.get_manual_bp())
    app.register_blueprint(season_router.get_bp())
