from typing import Optional
from pydantic import BaseModel

from model.file import FilePurpose


class VectorStoreMetadata(BaseModel):
    vector_store_id: str  # FilePurpose + leagueId (if LEAGUE)
    openai_vector_id: Optional[str] = None
    last_synced: Optional[str] = None


def generate_league_vector_store_id(league_id: str) -> str:
    return f"{FilePurpose.LEAGUE.value}_{league_id}"