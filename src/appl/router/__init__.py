from ..config.dependencies import (
    brief_store,
    chat_service,
    document_indexer,
    draft_service,
    espn_service,
    llm_factory,
    manual_store,
    schedule,
    token_store,
)
from ..ai.access import SessionAccess
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
    # Every router gets its collaborators from config/dependencies.py
    indexer, espn, store = document_indexer(), espn_service(), manual_store()
    main_router = MainRouter(indexer, store, espn)
    auth_router = AuthRouter(indexer)
    yahoo_router = YahooRouter(indexer)
    espn_router = EspnRouter(indexer, espn)
    access = SessionAccess(YahooLeagueRepository, store, EspnLeagueRepository)
    chat_router = ChatRouter(chat_service(), access)
    document_router = DocumentRouter(indexer, access)
    draft_router = DraftRouter(store, token_store(), espn, drafts=draft_service(), indexer=indexer)
    season_router = SeasonRouter(store, brief_store(), llm_factory, schedule(), espn, indexer=indexer)

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
