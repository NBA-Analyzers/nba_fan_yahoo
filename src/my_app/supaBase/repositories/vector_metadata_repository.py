# vector_metadata_repository.py
from typing import Optional, Dict, Any
from ..database.base_repository import BaseRepository


class VectorMetadataRepository(BaseRepository):
    def __init__(self):
        super().__init__("vector_metadata")

    def get_by_vector_store_id(self, vector_store_id: str) -> Optional[Dict[str, Any]]:
        """Get vector metadata by vector_store_id"""
        return self.get_by_field("vector_store_id", vector_store_id)

    def get_by_openai_vector_id(
        self, openai_vector_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get vector metadata by OpenAI vector ID"""
        return self.get_by_field("openai_vector_id", openai_vector_id)

    def update_by_vector_store_id(
        self, vector_store_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update vector metadata by vector_store_id"""
        return self.update_by_field("vector_store_id", vector_store_id, data)

    def delete_by_vector_store_id(self, vector_store_id: str) -> bool:
        """Delete vector metadata by vector_store_id"""
        return self.delete_by_field("vector_store_id", vector_store_id)
