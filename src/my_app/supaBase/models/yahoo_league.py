
# yahoo_league.py
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel

@dataclass
class YahooLeague(BaseModel):
    # Required fields first
    yahoo_user_id: str  # FK to yahoo_auth.yahoo_user_id
    league_id: str
    team_name: str
    # Optional fields last
    vector_store_league_id: Optional[str] = None  # FK → Vector_Metadata.vector_store_id
    created_at: Optional[str] = None