# file_services.py
from typing import List, Optional
from datetime import datetime
from ..models.vector_metadata import VectorMetadata
from ..models.file_metadata import FileMetadata
from ..repositories.vector_metadata_repository import VectorStoreMetadataRepository
from ..repositories.file_metadata_repository import FileMetadataRepository
from ..exceptions.custom_exceptions import (
    ValidationError,
    NotFoundError,
    DuplicateError,
)


class FileService:
    def __init__(self):
        self.vector_repo = VectorStoreMetadataRepository()
        self.file_repo = FileMetadataRepository()

    # ========== VECTOR STORE OPERATIONS ==========

    def create_vector_store(self, vector_metadata: VectorMetadata) -> VectorMetadata:
        """Create a new vector store"""
        # Validate required fields
        if not vector_metadata.vector_store_id:
            raise ValidationError("vector_store_id is required")
        if not vector_metadata.openai_vector_id:
            raise ValidationError("openai_vector_id is required")

        # Check if vector store already exists
        existing = self.vector_repo.get_by_vector_store_id(
            vector_metadata.vector_store_id
        )
        if existing:
            raise DuplicateError(
                f"Vector store '{vector_metadata.vector_store_id}' already exists"
            )

        # Create vector store
        created_data = self.vector_repo.create(vector_metadata.to_dict())
        return VectorMetadata.from_dict(created_data)

    def get_vector_store(self, vector_store_id: str) -> VectorMetadata:
        """Get vector store by ID"""
        data = self.vector_repo.get_by_vector_store_id(vector_store_id)
        if not data:
            raise NotFoundError(f"Vector store '{vector_store_id}' not found")
        return VectorMetadata.from_dict(data)

    def get_vector_store_by_openai_id(
        self, openai_vector_id: str
    ) -> Optional[VectorMetadata]:
        """Get vector store by OpenAI vector ID"""
        data = self.vector_repo.get_by_openai_vector_id(openai_vector_id)
        return VectorMetadata.from_dict(data) if data else None

    def update_vector_sync(self, vector_store_id: str) -> VectorMetadata:
        """Update the last_synced timestamp for a vector store"""
        existing = self.vector_repo.get_by_vector_store_id(vector_store_id)
        if not existing:
            raise NotFoundError(f"Vector store '{vector_store_id}' not found")

        # Update with current timestamp
        updated_data = self.vector_repo.update_by_vector_store_id(
            vector_store_id, {"last_synced": datetime.utcnow().isoformat()}
        )
        return VectorMetadata.from_dict(updated_data)

    def delete_vector_store(self, vector_store_id: str) -> bool:
        """Delete a vector store (will fail if files reference it)"""
        existing = self.vector_repo.get_by_vector_store_id(vector_store_id)
        if not existing:
            raise NotFoundError(f"Vector store '{vector_store_id}' not found")

        # Check if any files reference this vector store
        files = self.file_repo.get_by_vector_store_id(vector_store_id)
        if files:
            raise ValidationError(
                f"Cannot delete vector store '{vector_store_id}' - {len(files)} files reference it"
            )

        return self.vector_repo.delete_by_vector_store_id(vector_store_id)

    # ========== FILE METADATA OPERATIONS ==========

    def create_file_metadata(self, file_metadata: FileMetadata) -> FileMetadata:
        """Create new file metadata"""
        # Validate required fields
        if not file_metadata.file_id:
            raise ValidationError("file_id is required")
        if not file_metadata.openai_file_id:
            raise ValidationError("openai_file_id is required")
        if not file_metadata.vector_store_id:
            raise ValidationError("vector_store_id is required")

        # Validate that vector store exists (FK constraint)
        vector_store = self.vector_repo.get_by_vector_store_id(
            file_metadata.vector_store_id
        )
        if not vector_store:
            raise ValidationError(
                f"Vector store '{file_metadata.vector_store_id}' does not exist"
            )

        # Check if file already exists
        existing = self.file_repo.get_by_file_id(file_metadata.file_id)
        if existing:
            raise DuplicateError(f"File '{file_metadata.file_id}' already exists")

        # Create file metadata
        created_data = self.file_repo.create(file_metadata.to_dict())
        return FileMetadata.from_dict(created_data)

    def get_file_by_id(self, file_id: str) -> FileMetadata:
        """Get file metadata by file_id"""
        data = self.file_repo.get_by_file_id(file_id)
        if not data:
            raise NotFoundError(f"File '{file_id}' not found")
        return FileMetadata.from_dict(data)

    def get_file_by_openai_id(self, openai_file_id: str) -> Optional[FileMetadata]:
        """Get file metadata by OpenAI file ID"""
        data = self.file_repo.get_by_openai_file_id(openai_file_id)
        return FileMetadata.from_dict(data) if data else None

    def get_files_by_vector_store(self, vector_store_id: str) -> List[FileMetadata]:
        """Get all files for a vector store"""
        files_data = self.file_repo.get_by_vector_store_id(vector_store_id)
        return [FileMetadata.from_dict(data) for data in files_data]

    def get_files_by_league(self, league_id: str) -> List[FileMetadata]:
        """Get all files for a league"""
        files_data = self.file_repo.get_by_league_id(league_id)
        return [FileMetadata.from_dict(data) for data in files_data]

    def update_file_metadata(self, file_id: str, data: dict) -> FileMetadata:
        """Update file metadata"""
        existing = self.file_repo.get_by_file_id(file_id)
        if not existing:
            raise NotFoundError(f"File '{file_id}' not found")

        # If updating vector_store_id, validate it exists
        if "vector_store_id" in data:
            vector_store = self.vector_repo.get_by_vector_store_id(
                data["vector_store_id"]
            )
            if not vector_store:
                raise ValidationError(
                    f"Vector store '{data['vector_store_id']}' does not exist"
                )

        updated_data = self.file_repo.update_by_file_id(file_id, data)
        return FileMetadata.from_dict(updated_data)

    def delete_file_metadata(self, file_id: str) -> bool:
        """Delete file metadata"""
        existing = self.file_repo.get_by_file_id(file_id)
        if not existing:
            raise NotFoundError(f"File '{file_id}' not found")

        return self.file_repo.delete_by_file_id(file_id)

    # ========== COMBINED OPERATIONS ==========

    def create_file_with_vector_store(
        self, vector_metadata: VectorMetadata, file_metadata: FileMetadata
    ) -> tuple[VectorMetadata, FileMetadata]:
        """
        Create both vector store and file metadata atomically.
        Useful when uploading a new file to OpenAI.
        """
        # Ensure they reference each other correctly
        if vector_metadata.vector_store_id != file_metadata.vector_store_id:
            raise ValidationError(
                "vector_store_id mismatch between VectorMetadata and FileMetadata"
            )

        # Create vector store first (parent)
        created_vector = self.create_vector_store(vector_metadata)

        try:
            # Then create file (child)
            created_file = self.create_file_metadata(file_metadata)
            return created_vector, created_file
        except Exception as e:
            # Rollback: delete the vector store if file creation fails
            self.vector_repo.delete_by_vector_store_id(vector_metadata.vector_store_id)
            raise e

    def get_all_files_with_vector_info(
        self, league_id: Optional[str] = None
    ) -> List[dict]:
        """
        Get files with their associated vector store information.
        Optionally filter by league_id.
        """
        # Get files
        if league_id:
            files_data = self.file_repo.get_by_league_id(league_id)
        else:
            files_data = self.file_repo.get_all()

        # Enrich with vector store info
        result = []
        for file_data in files_data:
            file_obj = FileMetadata.from_dict(file_data)
            vector_data = self.vector_repo.get_by_vector_store_id(
                file_obj.vector_store_id
            )

            result.append(
                {
                    "file": file_obj.to_dict(),
                    "vector_store": VectorMetadata.from_dict(vector_data).to_dict()
                    if vector_data
                    else None,
                }
            )

        return result
