
from dataclasses import dataclass
from .base import BaseModel
from typing import Optional
@dataclass
class YahooAuth(BaseModel):
    yahoo_user_id: str
    access_token: str
    refresh_token: str
    created_at: Optional[str] = None