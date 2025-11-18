from typing import Optional

from openai import OpenAI

from ..repository.supaBase.repositories.vector_metadata_repository import (
    VectorStoreMetadataRepository,
)
from ..model.vector_store import VectorStoreMetadata
from datetime import datetime, timezone


class VectorStoreManager:
    def __init__(
        self,
        vector_store_respository: VectorStoreMetadataRepository,
        openai_client: OpenAI,
    ):
        self.vector_store_meatadata_repository = vector_store_respository
        self.openai_client = openai_client

    def update_vector_store(
        self, vector_store_metadata_id: str, openai_file_ids: list[str]
    ):
        openai_vector_store_id = self.create_vector_store_in_openai(
            vector_store_metadata_id, openai_file_ids
        )

        vector_store_metadata = (
            self.vector_store_meatadata_repository.get_by_vector_store_id(
                vector_store_metadata_id
            )
        )
        if vector_store_metadata is None:
            vector_store_metadata = VectorStoreMetadata(
                vector_store_id=vector_store_metadata_id
            )

        vector_store_metadata.openai_vector_id = openai_vector_store_id
        vector_store_metadata.last_synced = datetime.now(timezone.utc).isoformat()

        return self.vector_store_meatadata_repository.upsert_by_vector_store_id(
            vector_store_metadata_id, vector_store_metadata
        )

    def create_vector_store_in_openai(
        self, vector_store_metadata_id: str, openai_file_ids: list[str]
    ):
        vector_store = self.openai_client.vector_stores.create(
            name=vector_store_metadata_id
        )

        for file_id in openai_file_ids:
            self.openai_client.vector_stores.files.create(
                vector_store_id=vector_store.id, file_id=file_id
            )

        return vector_store.id

    def get_vector_store_by_id(
        self, vector_store_id: str
    ) -> Optional[VectorStoreMetadata]:
        return self.vector_store_meatadata_repository.get_by_vector_store_id(
            vector_store_id
        )
