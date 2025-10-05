# vector_metadata.py
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel


@dataclass
class VectorMetadata(BaseModel):
    # Required fields first
    vector_store_id: str
    openai_vector_id: str
    # Optional fields last
    created_at: Optional[str] = None
    last_synced: Optional[str] = None
