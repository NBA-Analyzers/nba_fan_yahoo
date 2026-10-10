import os
from pathlib import Path

from ..ai.chat_service import ChatService
from ..ai.document_indexer import DocumentIndexer
from ..ai.firestore_store import FirestoreVectorStore
from ..ai.litellm_adapters import LiteLLMClient, LiteLLMEmbedder
from ..ai.retrieval import RetrievalService
from ..ai.tools import manual_toolkit_factory
from ..draft.manual_league import default_store
from ..season.schedule import Schedule
from ..service.chat_session_manager import ChatSessionManager

_chat_session_manager = None
_retrieval_service = None
_chat_service = None
_document_indexer = None


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

    _chat_session_manager = ChatSessionManager()
    _retrieval_service = build_retrieval_service()
    _document_indexer = DocumentIndexer(_retrieval_service)
    _chat_service = ChatService(
        llm=LiteLLMClient.from_env(),
        retrieval=_retrieval_service,
        sessions=_chat_session_manager,
        system_prompt=load_system_prompt(),
        tools_factory=manual_toolkit_factory(default_store(), Schedule.load()),
    )


def chat_service() -> ChatService:
    return _chat_service


def document_indexer() -> DocumentIndexer:
    return _document_indexer


def retrieval_service() -> RetrievalService:
    return _retrieval_service


def chat_session_manager() -> ChatSessionManager:
    return _chat_session_manager
