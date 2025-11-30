
# Enhanced base_repository.py with better error handling
from abc import ABC
from typing import List, Dict, Any, Optional
from .connection import DatabaseManager
from ..exceptions.custom_exceptions import DatabaseError

class BaseRepository(ABC):
    
    def __init__(self, table_name: str):
        self.db = DatabaseManager().get_client()
        self.table_name = table_name
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record"""
        try:
            # Remove None values to let database handle defaults
            clean_data = {k: v for k, v in data.items() if v is not None}
            response = self.db.table(self.table_name).insert(clean_data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            raise DatabaseError(f"Failed to create record in {self.table_name}: {str(e)}")
    
    def get_by_field(self, field_name: str, value: Any) -> Optional[Dict[str, Any]]:
        """Get single record by field value"""
        try:
            response = self.db.table(self.table_name).select("*").eq(field_name, value).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get record from {self.table_name}: {str(e)}")
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all records from table"""
        try:
            response = self.db.table(self.table_name).select("*").execute()
            return response.data
        except Exception as e:
            raise DatabaseError(f"Failed to get records from {self.table_name}: {str(e)}")
    
    def update_by_field(self, field_name: str, field_value: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update record by field value"""
        try:
            # Remove None values and empty strings for updates
            clean_data = {k: v for k, v in data.items() if v is not None and v != ""}
            if not clean_data:
                raise DatabaseError("No valid data provided for update")
                
            response = self.db.table(self.table_name).update(clean_data).eq(field_name, field_value).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            raise DatabaseError(f"Failed to update record in {self.table_name}: {str(e)}")
    
    def update_by_two_fields(self, field1_name: str, field1_value: Any, field2_name: str, field2_value: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update record by two field values"""
        try:
            # Remove None values and empty strings for updates
            clean_data = {k: v for k, v in data.items() if v is not None and v != ""}
            if not clean_data:
                raise DatabaseError("No valid data provided for update")
                
            response = self.db.table(self.table_name).update(clean_data).eq(field1_name, field1_value).eq(field2_name, field2_value).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            raise DatabaseError(f"Failed to update record in {self.table_name}: {str(e)}")
        
    def delete_by_field(self, field_name: str, value: Any) -> bool:
        """Delete record by field value"""
        try:
            response = self.db.table(self.table_name).delete().eq(field_name, value).execute()
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete record from {self.table_name}: {str(e)}")
    
    def get_multiple_by_field(self, field_name: str, value: Any) -> List[Dict[str, Any]]:
        """Get multiple records by field value"""
        try:
            response = self.db.table(self.table_name).select("*").eq(field_name, value).execute()
            return response.data
        except Exception as e:
            raise DatabaseError(f"Failed to get multiple records from {self.table_name}: {str(e)}")
    
    def exists_by_field(self, field_name: str, value: Any) -> bool:
        """Check if record exists by field value"""
        try:
            response = self.db.table(self.table_name).select("*").eq(field_name, value).limit(1).execute()
            return len(response.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to check existence in {self.table_name}: {str(e)}")
    
    def get_by_two_fields(self, field1_name: str, field1_value: Any, field2_name: str, field2_value: Any) -> Optional[Dict[str, Any]]:
        """Get single record by two field values"""
        try:
            response = self.db.table(self.table_name).select("*").eq(field1_name, field1_value).eq(field2_name, field2_value).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            raise DatabaseError(f"Failed to get record from {self.table_name}: {str(e)}")