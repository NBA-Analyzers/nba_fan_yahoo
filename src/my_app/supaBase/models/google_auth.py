# google_auth.py
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel
from ..utils.validators import validate_email


@dataclass
class GoogleAuth(BaseModel):
    # Required fields first
    google_user_id: str
    full_name: str
    email: str
    access_token: str
    # Optional fields last
    created_at: Optional[str] = None
    last_updated: Optional[str] = None

    def __post_init__(self):
        if self.email:
            self.email = self.email.lower()
            validate_email(self.email)
