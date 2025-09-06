
# yahoo_auth.py
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel

@dataclass
class YahooAuth(BaseModel):
    # Required fields first
    yahoo_user_id: str
    access_token: str
    refresh_token: str
    # Optional fields last
    created_at: Optional[str] = None
