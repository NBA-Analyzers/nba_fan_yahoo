
from typing import List, Optional, Dict, Any
from ..database.base_repository import BaseRepository, DatabaseError

class GoogleFantasyRepository(BaseRepository):
    def __init__(self):
        super().__init__("google_fantasy")
    
    def get_by_google_user_id(self, google_user_id: str) -> List[Dict[str, Any]]:
        return self.get_multiple_by_field("google_user_id", google_user_id)
    
    def get_by_fantasy_user_id(self, fantasy_user_id: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("fantasy_user_id", fantasy_user_id)
    
    def get_by_google_and_platform(self, google_user_id: str, platform: str) -> Optional[Dict[str, Any]]:
        try:
            response = (self.db.table(self.table_name)
                       .select("*")
                       .eq("google_user_id", google_user_id)
                       .eq("fantasy_platform", platform)
                       .execute())
            return response.data[0] if response.data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get record: {str(e)}")
    
    def delete_by_google_and_platform(self, google_user_id: str, platform: str) -> bool:
        try:
            response = (self.db.table(self.table_name)
                       .delete()
                       .eq("google_user_id", google_user_id)
                       .eq("fantasy_platform", platform)
                       .execute())
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete record: {str(e)}")