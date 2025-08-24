
from dataclasses import dataclass
from typing import Optional
from .base import BaseModel
from utils.validators import validate_email


@dataclass
class GoogleAuth(BaseModel):
    google_user_id: str
    full_name: str
    email: str
    access_token: str

    
    def __post_init__(self):
        if self.email:
            self.email = self.email.lower()
            validate_email(self.email)