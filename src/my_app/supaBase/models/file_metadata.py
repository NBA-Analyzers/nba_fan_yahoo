# file_metadata.py
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel


@dataclass
class FileMetadata(BaseModel):
    # Required fields first
    file_id: str
    openai_file_id: str
    vector_store_id: str  # FK to vector_metadata.vector_store_id
    # Optional fields last
    file_name: Optional[str] = None
    league_id: Optional[str] = None
    file_path_BLOB: Optional[str] = None
    created_at: Optional[str] = None
