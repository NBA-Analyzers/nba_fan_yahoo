
# google_fantasy_repository.py
from typing import List, Optional, Dict, Any
from ..database.base_repository import BaseRepository, DatabaseError

class GoogleFantasyRepository(BaseRepository):
    def __init__(self):
        super().__init__("google_fantasy")
    
    def get_by_google_user_id(self, google_user_id: str) -> List[Dict[str, Any]]:
        """Get all fantasy platform connections for a Google user"""
        return self.get_multiple_by_field("google_user_id", google_user_id)
    
    def get_by_fantasy_user_id(self, fantasy_user_id: str) -> Optional[Dict[str, Any]]:
        """Get connection by fantasy user ID"""
        return self.get_by_field("fantasy_user_id", fantasy_user_id)
    
    def get_by_google_and_platform(self, google_user_id: str, platform: str) -> Optional[Dict[str, Any]]:
        """Get connection by Google user ID and platform"""
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
        """Delete connection by Google user ID and platform"""
        try:
            response = (self.db.table(self.table_name)
                       .delete()
                       .eq("google_user_id", google_user_id)
                       .eq("fantasy_platform", platform)
                       .execute())
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete record: {str(e)}")
    
    def get_by_composite_key(self, google_user_id: str, fantasy_user_id: str, fantasy_platform: str) -> Optional[Dict[str, Any]]:
        """Get connection by all three key fields (composite primary key)"""
        try:
            response = (self.db.table(self.table_name)
                       .select("*")
                       .eq("google_user_id", google_user_id)
                       .eq("fantasy_user_id", fantasy_user_id)
                       .eq("fantasy_platform", fantasy_platform)
                       .execute())
            return response.data[0] if response.data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get record: {str(e)}")
    
    def delete_by_composite_key(self, google_user_id: str, fantasy_user_id: str, fantasy_platform: str) -> bool:
        """Delete connection by composite primary key"""
        try:
            response = (self.db.table(self.table_name)
                       .delete()
                       .eq("google_user_id", google_user_id)
                       .eq("fantasy_user_id", fantasy_user_id)
                       .eq("fantasy_platform", fantasy_platform)
                       .execute())
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete record: {str(e)}")
    
    def get_google_users_by_yahoo_user(self, yahoo_user_id: str) -> List[Dict[str, Any]]:
        """Get all Google users connected to a specific Yahoo user"""
        try:
            response = (self.db.table(self.table_name)
                       .select("*")
                       .eq("fantasy_user_id", yahoo_user_id)
                       .eq("fantasy_platform", "yahoo")
                       .execute())
            return response.data
        except Exception as e:
            raise DatabaseError(f"Failed to get records: {str(e)}")

