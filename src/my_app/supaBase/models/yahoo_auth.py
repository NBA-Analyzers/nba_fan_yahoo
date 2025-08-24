
from dataclasses import dataclass
from .base import BaseModel

@dataclass
class YahooAuth(BaseModel):
    yahoo_user_id: str
    access_token: str
    refresh_token: str