from dataclasses import dataclass
from typing import Optional
from .base import BaseModel


@dataclass
class VectorMetadata(BaseModel):
    # Matches Supabase table: Vector_Metadata
    vector_store_id: str
    openai_vector_id: str
    created_at: Optional[str] = None


