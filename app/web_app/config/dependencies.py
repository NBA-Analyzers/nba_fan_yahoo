import os

from openai import OpenAI
from common.openai_file_manager import OpenaiFileManager
from common.repository.supaBase.repositories.vector_metadata_repository import vector_store_matadata_repository
from common.vector_store_manager import VectorStoreManager
from service.chat_session_manager import ChatSessionManager
from service.openai_agent_manager import OpenaiAgentManager

_openai_client = None
_openai_agent_manager = None
_openai_file_manager = None
_vector_store_manager = None
_chat_session_manager = None


def set_services():
    global \
        _openai_client, \
        _openai_agent_manager, \
        _openai_file_manager, \
        _vector_store_manager, \
        _chat_session_manager

    _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    _chat_session_manager = ChatSessionManager()
    _vector_store_manager = VectorStoreManager(
        vector_store_matadata_repository, _openai_client
    )
    _openai_file_manager = OpenaiFileManager(_vector_store_manager, _openai_client)
    _openai_agent_manager = OpenaiAgentManager(
        _chat_session_manager, _vector_store_manager, _openai_client
    )


def openai_client() -> OpenAI:
    return _openai_client


def openai_agent_manager() -> OpenaiAgentManager:
    return _openai_agent_manager


def openai_file_manager() -> OpenaiFileManager:
    return _openai_file_manager


def vector_store_manager() -> VectorStoreManager:
    return _vector_store_manager


def chat_session_manager() -> ChatSessionManager:
    return _chat_session_manager


