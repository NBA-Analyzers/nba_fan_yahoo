from curses import meta
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import openai
from openai import OpenAI
from openai.types import vector_store

from my_app.agent.api.files_api import LeagueFile
from my_app.agent.services.file_manager import FileMetadata

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
    ):
        openai_vector_store_id = self.create_vector_store_in_openai(openai_file_ids)
        
        #TODO: fetch from DB - vector store based on vector store id
        current_vector_store_metadata = None
        
        if current_vector_store_metadata is None:
            vector_store = VectorStoreMetadata(
                vector_store_id=vector_store_id,
                openai_vector_store_id=openai_vector_store_id
            )
            #TODO: save to vector_store DB
        else:
            self.client.vector_stores.delete(current_vector_store_metadata.openai_vector_store_id)
            #TODO: update DB with the new openai_vector_store_id



    def create_vector_store_in_openai(self, openai_file_ids: list[str]):
        vector_store = self.client.vector_stores.create()

        for file_id in openai_file_ids:
            self.client.vector_stores.files.create(
                vector_store_id=vector_store.id,
                file_id=file_id
            )

        return vector_store.id
