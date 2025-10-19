# vector_metadata_repository.py
from typing import Optional
from ....model.vector_store import VectorStoreMetadata
from ..database.base_repository import BaseRepository


class VectorStoreMetadataRepository(BaseRepository):
    def __init__(self):
        super().__init__("vector_metadata")

    def get_by_vector_store_id(
        self, vector_store_id: str
    ) -> Optional[VectorStoreMetadata]:
        """Get vector metadata by vector_store_id"""
        data = self.get_by_field("vector_store_id", vector_store_id)
        return VectorStoreMetadata(**data) if data else None

    def get_by_openai_vector_id(
        self, openai_vector_id: str
    ) -> Optional[VectorStoreMetadata]:
        """Get vector metadata by OpenAI vector ID"""
        data = self.get_by_field("openai_vector_id", openai_vector_id)
        return VectorStoreMetadata(**data) if data else None

    def upsert_by_vector_store_id(
        self, vector_store_id: str, data: VectorStoreMetadata
    ) -> Optional[VectorStoreMetadata]:
        """Update vector metadata by vector_store_id"""
        if self.exists_by_field("vector_store_id", vector_store_id):
            result = self.update_by_field("vector_store_id", vector_store_id, data.model_dump())
        else:
            result = self.create(data.model_dump())

        return VectorStoreMetadata(**result)

    def delete_by_vector_store_id(self, vector_store_id: str) -> bool:
        """Delete vector metadata by vector_store_id"""
        return self.delete_by_field("vector_store_id", vector_store_id)


vector_store_matadata_repository = VectorStoreMetadataRepository()
