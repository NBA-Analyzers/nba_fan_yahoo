# file_metadata_repository.py
from typing import List, Optional, Dict, Any
from ..database.base_repository import BaseRepository


class FileMetadataRepository(BaseRepository):
    def __init__(self):
        super().__init__("file_metadata")

    def get_by_file_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file metadata by file_id"""
        return self.get_by_field("file_id", file_id)

    def get_by_openai_file_id(self, openai_file_id: str) -> Optional[Dict[str, Any]]:
        """Get file metadata by OpenAI file ID"""
        return self.get_by_field("openai_file_id", openai_file_id)

    def get_by_vector_store_id(self, vector_store_id: str) -> List[Dict[str, Any]]:
        """Get all files for a vector store"""
        return self.get_multiple_by_field("vector_store_id", vector_store_id)

    def get_by_league_id(self, league_id: str) -> List[Dict[str, Any]]:
        """Get all files for a league"""
        return self.get_multiple_by_field("league_id", league_id)

    def update_by_file_id(self, file_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update file metadata by file_id"""
        return self.update_by_field("file_id", file_id, data)

    def delete_by_file_id(self, file_id: str) -> bool:
        """Delete file metadata by file_id"""
        return self.delete_by_field("file_id", file_id)
