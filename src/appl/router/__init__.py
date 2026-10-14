from ..config.dependencies import (
    chat_service,
    document_indexer,
)
from ..ai.access import SessionAccess
from ..fantasy_integrations.espn.espn_service import EspnService
from ..draft.manual_league import default_store
from ..ai.chat_router import ChatRouter
from ..repository.firestore import YahooLeagueRepository
from ..repository.firestore.espn_data import EspnLeagueRepository
from .auth_routes import AuthRouter
from .espn_routes import EspnRouter
from .draft_routes import DraftRouter
from .main_routes import MainRouter
from .season_routes import SeasonRouter
from .yahoo_routes import YahooRouter
from .document_router import DocumentRouter


def register_routes(app):
    """Register all route blueprints with the Flask app"""
    # Create router instances with dependencies
    manual_store = default_store()
    espn_service = EspnService(document_indexer())
    main_router = MainRouter(document_indexer(), manual_store, espn_service)
    auth_router = AuthRouter(document_indexer())
    yahoo_router = YahooRouter(document_indexer())
    espn_router = EspnRouter(document_indexer(), espn_service)
    access = SessionAccess(YahooLeagueRepository, manual_store, EspnLeagueRepository)
    chat_router = ChatRouter(chat_service(), access)
    document_router = DocumentRouter(document_indexer(), access)
    draft_router = DraftRouter(manual_store, espn=espn_service)
    season_router = SeasonRouter(manual_store, espn=espn_service)

    # Register blueprints
    app.register_blueprint(main_router.get_bp())
    app.register_blueprint(auth_router.get_bp())
    app.register_blueprint(yahoo_router.get_bp())
    app.register_blueprint(espn_router.get_bp())
    app.register_blueprint(chat_router.get_bp())
    app.register_blueprint(document_router.get_bp())
    app.register_blueprint(draft_router.get_bp())
    app.register_blueprint(draft_router.get_manual_bp())
    app.register_blueprint(season_router.get_bp())
