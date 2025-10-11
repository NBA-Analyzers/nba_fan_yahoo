from dataclasses import dataclass
from openai import OpenAI
from openai.types.vector_store import VectorStore


@dataclass
class VectorStoreMetadata:
    vector_store_id: str # FilePurpose + leagueId (if LEAGUE) 
    openai_vector_store_id: str

class VectorStoreManager():
    
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client

    def update_vector_store(
        self, 
        vector_store_id: str, 
        openai_file_ids: list[str]
    ) -> str:
        openai_vector_store_id = self.create_vector_store_in_openai(openai_file_ids)
        
        #TODO: fetch from DB - vector store based on vector store id
        current_vector_store_metadata = None
        
        if current_vector_store_metadata is None:
            current_vector_store_metadata = VectorStoreMetadata(
                vector_store_id=vector_store_id,
                openai_vector_store_id=openai_vector_store_id
            )
            #TODO: save to vector_store DB
        else:
            self.client.vector_stores.delete(current_vector_store_metadata.openai_vector_store_id)
            #TODO: update DB with the new openai_vector_store_id
        return openai_vector_store_id


    def create_vector_store_in_openai(self, openai_file_ids: list[str]):
        vector_store = self.client.vector_stores.create()

        for file_id in openai_file_ids:
            self.client.vector_stores.files.create(
                vector_store_id=vector_store.id,
                file_id=file_id
            )

        return vector_store.id