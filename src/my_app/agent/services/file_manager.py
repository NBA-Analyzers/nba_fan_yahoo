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
    def __init__(
        self,
        openai_client: OpenAI,
        vector_store_manager: VectorStoreManager,
        file_service=None,
    ):
        self.client = openai_client
        self.vector_store_manager = vector_store_manager
        self.file_service = file_service  # Optional: FileService for DB tracking

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
        # Save all file metadata to DB (if file_service available)
        if self.file_service:
            for file_meta in metadata:
                self._save_file_to_db(file_meta, vector_store_id, league_id=league_id)

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

        #: update metadata in DB
        vector_store_id = FilePurpose.RULES.value
        openai_file_ids = [md.openai_file_id for md in metadata]
        openai_vector_store_id = self.vector_store_manager.update_vector_store(
            FilePurpose.RULES, openai_file_ids
        )
        # Save file metadata to DB
        if self.file_service:
            for file_meta in metadata:
                self._save_file_to_db(file_meta, vector_store_id)

        return OpenaiStoredFiles(
            openai_vs_id=openai_vector_store_id, file_metadata=metadata
        )

    def update_box_score(self, file: UpdateFile) -> OpenaiStoredFiles:
        """
        Update box score file.
        Uploads to OpenAI and tracks in database.
        """
        openai_file_id, s3_path = self.update_file(file.file_name, file)

        file_metadata = FileMetadata(
            file_id=file.file_name,
            file_name=file.file_name,
            openai_file_id=openai_file_id,
            file_path_s3=s3_path,
        )

        # Create/update vector store
        vector_store_id = FilePurpose.BOX_SCORE.value
        openai_vector_store_id = self.vector_store_manager.update_vector_store(
            vector_store_id, [openai_file_id]
        )

        # Save to DB
        if self.file_service:
            self._save_file_to_db(file_metadata, vector_store_id)

        return OpenaiStoredFiles(
            openai_vs_id=openai_vector_store_id, file_metadata=[file_metadata]
        )

    def update_file(self, file_id: str, file: UpdateFile):
        #  fetch current file metadata based on file id
        current_file_metadata = None
        if self.file_service:
            try:
                existing = self.file_service.get_file_by_id(file_id)
                current_file_metadata = FileMetadata(
                    file_id=existing.file_id,
                    file_name=existing.file_name,
                    openai_file_id=existing.openai_file_id,
                    league_id=existing.league_id,
                    file_path_s3=existing.file_path_BLOB,
                )
            except Exception:
                # File not in DB yet
                pass

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

    def _save_file_to_db(
        self,
        file_meta: FileMetadata,
        vector_store_id: str,
        league_id: Optional[str] = None,
    ):
        """
        Internal method to save file metadata to database.
        Handles both new files and updates.
        """
        if not self.file_service:
            return

        try:
            from utils.db_config import DBFileMetadata

            db_file = DBFileMetadata(
                file_id=file_meta.file_id,
                openai_file_id=file_meta.openai_file_id,
                vector_store_id=vector_store_id,
                file_name=file_meta.file_name,
                league_id=league_id or file_meta.league_id,
                file_path_BLOB=file_meta.file_path_s3,
            )

            # Try to create, if exists then update
            try:
                self.file_service.create_file_metadata(db_file)
                print(f"✅ File metadata saved to DB: {file_meta.file_id}")
            except Exception:
                # File exists, update it
                self.file_service.update_file_metadata(
                    file_meta.file_id,
                    {
                        "openai_file_id": file_meta.openai_file_id,
                        "file_path_BLOB": file_meta.file_path_s3,
                    },
                )
                print(f"✅ File metadata updated in DB: {file_meta.file_id}")

        except Exception as e:
            print(f"⚠️  Failed to save file metadata to DB: {e}")
