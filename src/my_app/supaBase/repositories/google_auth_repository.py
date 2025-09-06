
from typing import Optional, Dict, Any
from ..database.base_repository import BaseRepository

class GoogleAuthRepository(BaseRepository):
    def __init__(self):
        super().__init__("google_auth")
    
    def get_by_google_user_id(self, google_user_id: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("google_user_id", google_user_id)
    
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("email", email.lower())
    
    def update_by_google_user_id(self, google_user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_by_field("google_user_id", google_user_id, data)
    
    def delete_by_google_user_id(self, google_user_id: str) -> bool:
        return self.delete_by_field("google_user_id", google_user_id)
