from io import BytesIO
import json
from typing import Dict

from openai import OpenAI

from service.vector_store_manager import VectorStoreManager
from model.vector_store import generate_league_vector_store_id
from model.file import FilePurpose


class OpenaiFileManager:

    def __init__(self, vector_store_manager: VectorStoreManager, openai_client: OpenAI):
        self.vector_store_manager = vector_store_manager
        self.openai_client = openai_client

    def update_league_files(self, league_id: str, files: Dict[str, any]):
        openai_file_ids = []

        for file_name, file_content in files.items():
            openai_file_ids.append(self.upload_file_in_openai(file_name, file_content))

        vector_store_id = generate_league_vector_store_id(league_id)
        self.vector_store_manager.update_vector_store(vector_store_id, openai_file_ids)

    def update_rules(self, file: Dict[str, str]):
        openai_file_id = self.upload_file_in_openai("rules", file)

        vector_store_id = FilePurpose.RULES.value
        self.vector_store_manager.update_vector_store(vector_store_id, [openai_file_id])

    def update_box_score(self, files: Dict[str, Dict[str, str]]):
        openai_file_ids = []

        for file_name, file_content in files:
            openai_file_ids.append(self.upload_file_in_openai(file_name, file_content))

        vector_store_id = FilePurpose.BOX_SCORE.value
        self.vector_store_manager.update_vector_store(vector_store_id, openai_file_ids)

    def upload_file_in_openai(self, file_name: str, file_content: any):
        json_content = json.dumps(file_content, ensure_ascii=False)
        file_object = BytesIO(json_content.encode("utf-8"))
        file_object.name = f"{file_name}.json"
        openai_file = self.openai_client.files.create(
            file=file_object, 
            purpose="assistants")
        return openai_file.id
