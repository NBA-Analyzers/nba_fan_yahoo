
from dataclasses import dataclass
from .base import BaseModel
from utils.validators import validate_platform

@dataclass
class GoogleFantasy(BaseModel):
    google_user_id: str
    fantasy_user_id: str  # FK to yahoo_auth.yahoo_user_id
    fantasy_platform: str
    
    def __post_init__(self):
        validate_platform(self.fantasy_platform)
