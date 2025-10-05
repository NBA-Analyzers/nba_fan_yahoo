from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from openai import OpenAI
from openai.types.vector_store import VectorStore


@dataclass
class VectorStoreMetadata:
    vector_store_id: str  # FilePurpose + leagueId (if LEAGUE)
    openai_vector_store_id: str


class VectorStoreManager:
    def __init__(self, openai_client: OpenAI, file_service=None):
        self.client = openai_client
        self.file_service = file_service  # Optional: FileService for DB tracking

    def update_vector_store(
        self, vector_store_id: str, openai_file_ids: list[str]
    ) -> str:
        openai_vector_store_id = self.create_vector_store_in_openai(openai_file_ids)

        # fetch from DB - vector store based on vector store id
        current_vector_store_metadata = None
        if self.file_service:
            try:
                existing = self.file_service.get_vector_store(vector_store_id)
                current_vector_store_metadata = VectorStoreMetadata(
                    vector_store_id=existing.vector_store_id,
                    openai_vector_store_id=existing.openai_vector_id,
                )
            except Exception:
                # Not found in DB, will create new
                pass

        if current_vector_store_metadata is None:
            # Create new vector store metadata
            new_metadata = VectorStoreMetadata(
                vector_store_id=vector_store_id,
                openai_vector_store_id=openai_vector_store_id,
            )

            # Save to database if file_service is available
            if self.file_service:
                try:
                    from datetime import datetime
                    from utils.db_config import DBVectorMetadata

                    db_vector = DBVectorMetadata(
                        vector_store_id=vector_store_id,
                        openai_vector_id=openai_vector_store_id,
                        last_synced=datetime.utcnow().isoformat(),  # Set on creation
                    )
                    self.file_service.create_vector_store(db_vector)
                    print(f"✅ Vector store saved to DB: {vector_store_id}")
                except Exception as e:
                    print(f"⚠️  Failed to save vector store to DB: {e}")
                    # Continue anyway - OpenAI operation succeeded
        else:
            self.client.vector_stores.delete(
                current_vector_store_metadata.openai_vector_store_id
            )
            # update DB with the new openai_vector_store_id
            if self.file_service:
                try:
                    self.file_service.update_vector_sync(vector_store_id)
                    print(f"✅ Vector store updated in DB: {vector_store_id}")
                except Exception as e:
                    print(f"⚠️  Failed to update vector store in DB: {e}")
        return openai_vector_store_id

    def create_vector_store_in_openai(self, openai_file_ids: list[str]):
        vector_store = self.client.vector_stores.create()

        for file_id in openai_file_ids:
            self.client.vector_stores.files.create(
                vector_store_id=vector_store.id, file_id=file_id
            )

        return vector_store.id

    def get_vector_store_id(self, vector_store_id: str) -> Optional[str]:
        """
        Get OpenAI vector store ID from database.
        Falls back to None if not found.

        """
        if not self.file_service:
            return None

        try:
            vector_meta = self.file_service.get_vector_store(vector_store_id)
            return vector_meta.openai_vector_id
        except Exception:
            return None
