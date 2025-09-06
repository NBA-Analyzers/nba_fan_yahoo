
from typing import Optional, Dict, Any
from ..database.base_repository import BaseRepository

class YahooAuthRepository(BaseRepository):
    def __init__(self):
        super().__init__("yahoo_auth")
    
    def get_by_yahoo_user_id(self, yahoo_user_id: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("yahoo_user_id", yahoo_user_id)
    
    def update_by_yahoo_user_id(self, yahoo_user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_by_field("yahoo_user_id", yahoo_user_id, data)
    
    def delete_by_yahoo_user_id(self, yahoo_user_id: str) -> bool:
        return self.delete_by_field("yahoo_user_id", yahoo_user_id)
