from dataclasses import dataclass
from enum import Enum
from typing import Optional
from openai import OpenAI

from services.vector_store_manager import VectorStoreManager


class FilePurpose(Enum):
    BOX_SCORE = "box_score"
    RULES = "rules"
    LEAGUE = "league"


@dataclass
class FileMetadata:
    file_id: str
    file_name: str
    openai_file_id: str
    league_id: Optional[str]
    file_path_s3: str


@dataclass
class UpdateFile:
    file_name: str
    file_path: str


@dataclass
class OpenaiStoredFiles:
    openai_vs_id: str
    file_metadata: list[FileMetadata]


class FileManager:
    def __init__(self, openai_client: OpenAI, vector_store_manager: VectorStoreManager):
        self.client = openai_client
        self.vector_store_manager = vector_store_manager

    def update_league_files(
        self, league_id: str, files: list[UpdateFile]
    ) -> OpenaiStoredFiles:
        metadata = []

        for file in files:
            file_id = f"{file.file_name}_{league_id}"
            openai_file_id, s3_path = self.update_file(file_id, file)
            metadata.append(
                FileMetadata(
                    file_id=file_id,
                    file_name=file.file_name,
                    openai_file_id=openai_file_id,
                    league_id=league_id,
                    file_path_s3=s3_path,
                )
            )

        # TODO: upsert metadata in DB

        vector_store_id = f"{FilePurpose.LEAGUE.value}_{league_id}"
        openai_file_ids = [md.openai_file_id for md in metadata]
        openai_vector_store_id = self.vector_store_manager.update_vector_store(
            vector_store_id, openai_file_ids
        )
        return OpenaiStoredFiles(
            openai_vs_id=openai_vector_store_id, file_metadata=metadata
        )

    def update_rules(self, files: list[UpdateFile]) -> OpenaiStoredFiles:
        metadata = []

        for file in files:
            openai_file_id, s3_path = self.update_file(file)
            metadata.append(
                FileMetadata(
                    file_id=file.file_name,
                    file_name=file.file_name,
                    openai_file_id=openai_file_id,
                    file_path_s3=s3_path,
                )
            )

        # TODO: update metadata in DB
        openai_file_ids = [md.openai_file_id for md in metadata]
        openai_vector_store_id = self.vector_store_manager.update_vector_store(
            FilePurpose.RULES, openai_file_ids
        )
        return OpenaiStoredFiles(
            openai_vs_id=openai_vector_store_id, file_metadata=metadata
        )

    def update_box_score(self, file: UpdateFile) -> OpenaiStoredFiles:
        openai_file_id, s3_path = self.update_file(file)

        # TODO: update metadata in DB
        openai_vector_store_id = self.vector_store_manager.update_vector_store(
            FilePurpose.BOX_SCORE, [openai_file_id]
        )
        return OpenaiStoredFiles(
            openai_vs_id=openai_vector_store_id,
            file_metadata=[
                FileMetadata(
                    file_id=file.file_name,
                    file_name=file.file_name,
                    openai_file_id=openai_file_id,
                    file_path_s3=s3_path,
                )
            ],
        )

    def update_file(self, file_id: str, file: UpdateFile):
        # TODO: fetch current file metadata based on file id
        current_file_metadata = None

        s3_path = ""  # upsert (override or upload) file to S3
        openai_file_id = self.upload_file_in_openai(file.file_path)

        # remove existing
        if current_file_metadata is not None:
            self.client.files.delete(current_file_metadata.openai_file_id)

        return openai_file_id, s3_path

    def upload_file_in_openai(self, file_path: str):
        with open(file_path, "rb") as f:
            openai_file = self.client.files.create(file=f, purpose="assistants")
        return openai_file.id
