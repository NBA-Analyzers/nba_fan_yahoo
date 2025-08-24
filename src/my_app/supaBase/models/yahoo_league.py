from dataclasses import dataclass
from .base import BaseModel

@dataclass
class YahooLeague(BaseModel):
    yahoo_user_id: str  # FK to yahoo_auth.yahoo_user_id
    league_id: str
    team_name: str
