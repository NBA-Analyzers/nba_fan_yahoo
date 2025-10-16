from enum import Enum
from typing import Optional
from pydantic import BaseModel

class VectorStorePurpose(Enum):
    BOX_SCORE = "box_score"
    RULES = "rules"
    LEAGUE = "league"

class VectorStoreMetadata(BaseModel):
    vector_store_id: str
    openai_vector_id: Optional[str] = None
    last_synced: Optional[str] = None


def generate_league_vector_store_id(league_id: str) -> str:
    return f"{VectorStorePurpose.LEAGUE.value}_{league_id}"