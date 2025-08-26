from dataclasses import dataclass
from .base import BaseModel
from typing import Optional
@dataclass
class YahooLeague(BaseModel):
    yahoo_user_id: str  # FK to yahoo_auth.yahoo_user_id
    league_id: str
    team_name: str
    created_at: Optional[str] = None