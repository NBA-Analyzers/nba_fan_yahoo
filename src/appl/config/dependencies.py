import os
from pathlib import Path

from ..ai.chat_service import ChatService
from ..ai.document_indexer import DocumentIndexer
from ..ai.firestore_store import FirestoreVectorStore
from ..ai.litellm_adapters import LiteLLMClient, LiteLLMEmbedder
from ..ai.retrieval import RetrievalService
from ..ai.tools import league_toolkit_factory
from ..draft.api_tokens import ApiTokenStore, default_token_store
from ..draft.manual_league import ManualLeagueStore, default_store as default_manual_store
from ..draft.service import DraftService
from ..fantasy_integrations.espn.espn_service import EspnService
from ..season import report_writer
from ..season.schedule import Schedule
from ..service.chat_session_manager import ChatSessionManager, default_store

_chat_session_manager = None
_retrieval_service = None
_chat_service = None
_document_indexer = None
_manual_store = None
_espn_service = None
_schedule = None
_draft_service = None
_brief_store = None
_token_store = None


def load_system_prompt() -> str:
    default_prompt_path = Path(__file__).resolve().parent.parent / "utils" / "system_prompt.md"
    env_prompt_path = os.environ.get("SYSTEM_PROMPT_PATH")
    path = Path(env_prompt_path).expanduser() if env_prompt_path else default_prompt_path
    return path.read_text(encoding="utf-8")


def build_retrieval_service() -> RetrievalService:
    from google.cloud import firestore

    client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return RetrievalService(
        embedder=LiteLLMEmbedder.from_env(),
        store=FirestoreVectorStore(client),
        top_k=int(os.environ.get("RETRIEVAL_TOP_K", 5)),
    )


def set_services():
    global _chat_session_manager, _retrieval_service, _chat_service, _document_indexer
    global _manual_store, _espn_service, _schedule, _draft_service, _brief_store, _token_store

    _chat_session_manager = ChatSessionManager(default_store())
    _retrieval_service = build_retrieval_service()
    _document_indexer = DocumentIndexer(_retrieval_service)
    _chat_service = ChatService(
        llm=LiteLLMClient.from_env(),
        retrieval=_retrieval_service,
        sessions=_chat_session_manager,
        system_prompt=load_system_prompt(),
    )

    # Everything the routes share is built here, once
    _manual_store = default_manual_store()
    _espn_service = EspnService(_document_indexer)
    _schedule = Schedule.load()
    _draft_service = DraftService()
    _brief_store = report_writer.BriefStore()
    _token_store = default_token_store()
    # The chat gets the season tools for every league type
    _chat_service.tools_factory = league_toolkit_factory(_manual_store, _espn_service, _schedule)


def chat_service() -> ChatService:
    return _chat_service


def document_indexer() -> DocumentIndexer:
    return _document_indexer


def retrieval_service() -> RetrievalService:
    return _retrieval_service


def chat_session_manager() -> ChatSessionManager:
    return _chat_session_manager


def manual_store() -> ManualLeagueStore:
    return _manual_store


def espn_service() -> EspnService:
    return _espn_service


def schedule() -> Schedule:
    return _schedule


def draft_service() -> DraftService:
    return _draft_service


def brief_store() -> report_writer.BriefStore:
    return _brief_store


def token_store() -> ApiTokenStore:
    return _token_store


def llm_factory() -> LiteLLMClient:
    """A fresh model client for one request; the season brief asks for it when needed."""
    return LiteLLMClient.from_env()
