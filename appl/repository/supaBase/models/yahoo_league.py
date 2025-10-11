
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
    created_at: Optional[str] = None