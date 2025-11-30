from io import BytesIO
import json
from typing import Any, Dict

from openai import OpenAI

from .vector_store_manager import VectorStoreManager
from ..model.vector_store import generate_league_vector_store_id
from ..model.file import FilePurpose


class OpenaiFileManager:
    def __init__(self, vector_store_manager: VectorStoreManager, openai_client: OpenAI):
        self.vector_store_manager = vector_store_manager
        self.openai_client = openai_client

    def _upload_local_file(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            openai_file = self.openai_client.files.create(file=f, purpose="assistants")
        return openai_file.id

    def update_league_files(self, league_id: str, files: Dict[str, any]):
        openai_file_ids = []

        for file_name, file_content in files.items():
            openai_file_ids.append(self.upload_file_in_openai(file_name, file_content))

        vector_store_id = generate_league_vector_store_id(league_id)
        self.vector_store_manager.update_vector_store(vector_store_id, openai_file_ids)

    def update_rules(self, pdf_path: str):
        openai_file_id = self._upload_local_file(pdf_path)
        vector_store_id = FilePurpose.GENERAL.value
        vector_store_metadata = self.vector_store_manager.update_vector_store(
            vector_store_id, [openai_file_id]
        )
        return vector_store_metadata

    def update_player_stats(self, json_path: str, pdf_path: str | None = None):
        openai_file_ids = [self._upload_local_file(json_path)]
        if pdf_path:
            openai_file_ids.append(self._upload_local_file(pdf_path))

        vector_store_id = FilePurpose.GENERAL.value
        vector_store_metadata = self.vector_store_manager.update_vector_store(
            vector_store_id, openai_file_ids
        )
        return vector_store_metadata

    def upload_file_in_openai(self, file_name: str, file_content: any):
        json_content = json.dumps(file_content, ensure_ascii=False)
        file_object = BytesIO(json_content.encode("utf-8"))
        file_object.name = f"{file_name}.json"
        openai_file = self.openai_client.files.create(
            file=file_object, purpose="assistants"
        )
        return openai_file.id
