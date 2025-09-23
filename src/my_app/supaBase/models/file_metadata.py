from dataclasses import dataclass
from typing import Optional
from .base import BaseModel


@dataclass
class FileMetadata(BaseModel):
    # Matches Supabase table: File_Metadata
    file_id: str
    openai_file_id: str
    vector_store_id: Optional[str]
    file_name: Optional[str]
    league_id: Optional[str]
    file_path_BLOB: Optional[str]
    created_at: Optional[str] = None


