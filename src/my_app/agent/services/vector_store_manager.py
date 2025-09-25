from dataclasses import dataclass
from openai import OpenAI
from openai.types.vector_store import VectorStore

from my_app.agent.api.files_api import LeagueFile
from my_app.agent.services.file_manager import FileMetadata
from my_app.agent.services.file_manager import FilePurpose
from my_app.supaBase.repositories.vector_metadata_repository import VectorMetadataRepository
from my_app.supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
@dataclass
class VectorStoreMetadata:
    vector_store_id: str # FilePurpose + leagueId (if LEAGUE) 
    openai_vector_store_id: str

class VectorStoreManager():
    
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        self._vector_repo = VectorMetadataRepository()
        self._yahoo_league_repo = YahooLeagueRepository()

    def update_vector_store(self, vector_store_id: str, openai_file_ids: list[str]):
        # Check current mapping
        current_vector_store_metadata = self._vector_repo.get_by_vector_store_id(vector_store_id)

        # If exists, delete old OpenAI vector store to avoid resource leak
        if current_vector_store_metadata and current_vector_store_metadata.get("openai_vector_id"):
            try:
                self.client.vector_stores.delete(current_vector_store_metadata["openai_vector_id"])
            except Exception:
                pass

        # Create new vector store and link files
        openai_vector_store_id = self.create_vector_store_in_openai(openai_file_ids)

        # Upsert mapping in DB
        self._vector_repo.upsert({
            "vector_store_id": vector_store_id,
            "openai_vector_id": openai_vector_store_id
        })

        # If this is a league vector store, persist the link on YahooLeague
        league_prefixes = [f"{FilePurpose.LEAGUE}", f"{FilePurpose.LEAGUE.value}"]
        for prefix in league_prefixes:
            if str(vector_store_id).startswith(f"{prefix}_"):
                league_id = str(vector_store_id).split("_", 1)[1]
                try:
                    self._yahoo_league_repo.update_by_league_id(league_id, {
                        "vector_store_league_id": vector_store_id
                    })
                except Exception:
                    pass
                break



    def create_vector_store_in_openai(self, openai_file_ids: list[str]):
        vector_store = self.client.vector_stores.create()

        for file_id in openai_file_ids:
            self.client.vector_stores.files.create(
                vector_store_id=vector_store.id,
                file_id=file_id
            )

        return vector_store.id