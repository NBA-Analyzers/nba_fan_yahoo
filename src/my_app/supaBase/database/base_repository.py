
from abc import ABC
from typing import List, Dict, Any, Optional
from database.connection import DatabaseManager
from exceptions.custom_exceptions import DatabaseError

class BaseRepository(ABC):
    def __init__(self, table_name: str):
        self.db = DatabaseManager().get_client()
        self.table_name = table_name
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self.db.table(self.table_name).insert(data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            raise DatabaseError(f"Failed to create record in {self.table_name}: {str(e)}")
    
    def get_by_field(self, field_name: str, value: Any) -> Optional[Dict[str, Any]]:
        try:
            response = self.db.table(self.table_name).select("*").eq(field_name, value).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get record from {self.table_name}: {str(e)}")
    
    def get_all(self) -> List[Dict[str, Any]]:
        try:
            response = self.db.table(self.table_name).select("*").execute()
            return response.data
        except Exception as e:
            raise DatabaseError(f"Failed to get records from {self.table_name}: {str(e)}")
    
    def update_by_field(self, field_name: str, field_value: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self.db.table(self.table_name).update(data).eq(field_name, field_value).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            raise DatabaseError(f"Failed to update record in {self.table_name}: {str(e)}")
    
    def delete_by_field(self, field_name: str, value: Any) -> bool:
        try:
            response = self.db.table(self.table_name).delete().eq(field_name, value).execute()
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete record from {self.table_name}: {str(e)}")
    
    def get_multiple_by_field(self, field_name: str, value: Any) -> List[Dict[str, Any]]:
        try:
            response = self.db.table(self.table_name).select("*").eq(field_name, value).execute()
            return response.data
        except Exception as e:
            raise DatabaseError(f"Failed to get multiple records from {self.table_name}: {str(e)}")
