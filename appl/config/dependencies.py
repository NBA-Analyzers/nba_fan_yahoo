from service.agent_manager import AgentManager
from service.file_manager import FileManager
from service.vector_store_manager import VectorStoreManager


_agent_manager = None
_file_manager = None
_vector_store_manager = None

def set_services(agent_manager: AgentManager, file_manager: FileManager, vector_store_manager: VectorStoreManager):
    global _agent_manager, _file_manager, _vector_store_manager
    _agent_manager = agent_manager
    _file_manager = file_manager
    _vector_store_manager = vector_store_manager

def get_agent_manager() -> AgentManager:
    return _agent_manager

def get_file_manager() -> FileManager:
    return _file_manager

def get_vector_store_manager() -> VectorStoreManager:
    return _vector_store_manager