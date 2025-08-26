
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel
from ..utils.validators import validate_platform

@dataclass
class GoogleFantasy(BaseModel):
    google_user_id: str  # FK to google_auth.google_user_id
    fantasy_user_id: str  # FK to yahoo_auth.yahoo_user_id (or other platform user ID)
    fantasy_platform: str
    created_at: Optional[str] = None
    
    def __post_init__(self):
        validate_platform(self.fantasy_platform)