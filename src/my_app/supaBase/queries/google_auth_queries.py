"""
Google Auth Supabase Database Operations - Python Implementation
Converted from JavaScript to Python with structured functions for google_auth table
"""

import os
from typing import Dict, List, Optional, Union, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from supabase import create_client, Client
from postgrest.exceptions import APIError
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class GoogleAuthUser:
    """Data class for Google Auth user structure"""
    google_user_id: str
    full_name: str
    email: str
    access_token: str
    created_at: Optional[str] = None

@dataclass
class DatabaseResponse:
    """Standardized response for database operations"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    count: Optional[int] = None

class GoogleAuthManager:
    """Manager class for Google Auth table operations"""
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase client for Google Auth operations
        
        Args:
            url: Supabase project URL
            key: Supabase anon key
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_KEY')
        self.table_name = 'google_auth'
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be provided or set as environment variables")
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
            logger.info("Google Auth Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

    def _handle_response(self, response, operation: str = "operation") -> DatabaseResponse:
        """Handle and standardize Supabase responses"""
        try:
            if hasattr(response, 'data'):
                count = len(response.data) if isinstance(response.data, list) else (1 if response.data else 0)
                logger.info(f"{operation} successful - {count} records affected")
                return DatabaseResponse(
                    success=True,
                    data=response.data,
                    count=count
                )
            else:
                logger.warning(f"{operation} returned no data")
                return DatabaseResponse(success=False, error="No data returned")
        except Exception as e:
            logger.error(f"{operation} failed: {e}")
            return DatabaseResponse(success=False, error=str(e))

    # READ OPERATIONS
    
    def read_all_rows(self) -> DatabaseResponse:
        """
        Read all rows from google_auth table
        Equivalent to: supabase.from('google_auth').select('*')
        """
        try:
            response = self.supabase.table(self.table_name).select("*").execute()
            return self._handle_response(response, "Read all rows")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_specific_columns(self, columns: List[str]) -> DatabaseResponse:
        """
        Read specific columns from google_auth table
        
        Args:
            columns: List of column names to select
            
        Equivalent to: supabase.from('google_auth').select('some_column,other_column')
        """
        try:
            column_str = ",".join(columns)
            response = self.supabase.table(self.table_name).select(column_str).execute()
            return self._handle_response(response, f"Read columns: {column_str}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_with_pagination(self, start: int = 0, end: int = 9) -> DatabaseResponse:
        """
        Read rows with pagination
        
        Args:
            start: Starting index (inclusive)
            end: Ending index (inclusive)
            
        Equivalent to: supabase.from('google_auth').select('*').range(0, 9)
        """
        try:
            response = self.supabase.table(self.table_name).select("*").range(start, end).execute()
            return self._handle_response(response, f"Read with pagination ({start}-{end})")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # FILTERING OPERATIONS
    
    def filter_equal(self, column: str, value: Any) -> DatabaseResponse:
        """Filter rows where column equals value"""
        try:
            response = self.supabase.table(self.table_name).select("*").eq(column, value).execute()
            return self._handle_response(response, f"Filter {column} = {value}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_greater_than(self, column: str, value: Any) -> DatabaseResponse:
        """Filter rows where column > value"""
        try:
            response = self.supabase.table(self.table_name).select("*").gt(column, value).execute()
            return self._handle_response(response, f"Filter {column} > {value}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_less_than(self, column: str, value: Any) -> DatabaseResponse:
        """Filter rows where column < value"""
        try:
            response = self.supabase.table(self.table_name).select("*").lt(column, value).execute()
            return self._handle_response(response, f"Filter {column} < {value}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_like(self, column: str, pattern: str, case_sensitive: bool = True) -> DatabaseResponse:
        """
        Filter rows with LIKE pattern matching
        
        Args:
            column: Column name
            pattern: Pattern to match (use % for wildcards)
            case_sensitive: Whether to use case-sensitive matching
        """
        try:
            if case_sensitive:
                response = self.supabase.table(self.table_name).select("*").like(column, pattern).execute()
            else:
                response = self.supabase.table(self.table_name).select("*").ilike(column, pattern).execute()
            return self._handle_response(response, f"Filter {column} LIKE {pattern}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_in_list(self, column: str, values: List[Any]) -> DatabaseResponse:
        """Filter rows where column value is in the provided list"""
        try:
            response = self.supabase.table(self.table_name).select("*").in_(column, values).execute()
            return self._handle_response(response, f"Filter {column} IN {values}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_is_null(self, column: str) -> DatabaseResponse:
        """Filter rows where column is NULL"""
        try:
            response = self.supabase.table(self.table_name).select("*").is_(column, None).execute()
            return self._handle_response(response, f"Filter {column} IS NULL")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_not_equal(self, column: str, value: Any) -> DatabaseResponse:
        """Filter rows where column != value"""
        try:
            response = self.supabase.table(self.table_name).select("*").neq(column, value).execute()
            return self._handle_response(response, f"Filter {column} != {value}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def complex_filter(self, filters: Dict[str, Any]) -> DatabaseResponse:
        """
        Apply multiple filters
        
        Args:
            filters: Dictionary with filter conditions
            Example: {
                'email': 'user@example.com',
                'full_name__like': '%John%',
                'created_at__gt': '2024-01-01'
            }
        """
        try:
            query = self.supabase.table(self.table_name).select("*")
            
            for key, value in filters.items():
                if '__' in key:
                    column, operator = key.split('__', 1)
                    if operator == 'like':
                        query = query.like(column, value)
                    elif operator == 'ilike':
                        query = query.ilike(column, value)
                    elif operator == 'gt':
                        query = query.gt(column, value)
                    elif operator == 'lt':
                        query = query.lt(column, value)
                    elif operator == 'gte':
                        query = query.gte(column, value)
                    elif operator == 'lte':
                        query = query.lte(column, value)
                    elif operator == 'neq':
                        query = query.neq(column, value)
                    elif operator == 'in':
                        query = query.in_(column, value)
                else:
                    query = query.eq(key, value)
            
            response = query.execute()
            return self._handle_response(response, f"Complex filter with {len(filters)} conditions")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # INSERT OPERATIONS
    
    def insert_single_row(self, user_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Insert a single row
        
        Args:
            user_data: Dictionary containing user data
            
        Equivalent to: supabase.from('google_auth').insert([{...}]).select()
        """
        try:
            # Add created_at if not provided
            if 'created_at' not in user_data:
                user_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert([user_data]).select().execute()
            return self._handle_response(response, "Insert single row")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def insert_google_user(self, google_user_id: str, full_name: str, email: str, 
                          access_token: str) -> DatabaseResponse:
        """
        Insert a Google user with proper validation
        
        Args:
            google_user_id: Google user ID
            full_name: User's full name
            email: User's email
            access_token: Google access token
        """
        user_data = {
            'google_user_id': google_user_id,
            'full_name': full_name,
            'email': email,
            'access_token': access_token,
            'created_at': datetime.utcnow().isoformat()
        }
        
        return self.insert_single_row(user_data)

    def insert_multiple_rows(self, users_data: List[Dict[str, Any]]) -> DatabaseResponse:
        """
        Insert multiple rows
        
        Args:
            users_data: List of user data dictionaries
            
        Equivalent to: supabase.from('google_auth').insert([{...}, {...}]).select()
        """
        try:
            # Add created_at to each record if not provided
            for user_data in users_data:
                if 'created_at' not in user_data:
                    user_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert(users_data).select().execute()
            return self._handle_response(response, f"Insert {len(users_data)} rows")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def upsert_user(self, user_data: Dict[str, Any], 
                   conflict_column: str = 'google_user_id') -> DatabaseResponse:
        """
        Upsert (insert or update) a user
        
        Args:
            user_data: User data dictionary
            conflict_column: Column to check for conflicts
            
        Equivalent to: supabase.from('google_auth').upsert({...}).select()
        """
        try:
            if 'created_at' not in user_data:
                user_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).upsert(user_data).select().execute()
            return self._handle_response(response, "Upsert user")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # UPDATE OPERATIONS
    
    def update_user_by_id(self, google_user_id: str, 
                         update_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Update user by Google user ID
        
        Args:
            google_user_id: Google user ID to update
            update_data: Data to update
            
        Equivalent to: supabase.from('google_auth').update({...}).eq('google_user_id', id).select()
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update(update_data)
                       .eq('google_user_id', google_user_id)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update user {google_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def update_user_by_email(self, email: str, 
                            update_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Update user by email
        
        Args:
            email: User email to update
            update_data: Data to update
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update(update_data)
                       .eq('email', email)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update user with email {email}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def update_access_token(self, google_user_id: str, new_token: str) -> DatabaseResponse:
        """
        Update access token for a specific user
        
        Args:
            google_user_id: Google user ID
            new_token: New access token
        """
        return self.update_user_by_id(google_user_id, {'access_token': new_token})

    # DELETE OPERATIONS
    
    def delete_user_by_id(self, google_user_id: str) -> DatabaseResponse:
        """
        Delete user by Google user ID
        
        Args:
            google_user_id: Google user ID to delete
            
        Equivalent to: supabase.from('google_auth').delete().eq('google_user_id', id)
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('google_user_id', google_user_id)
                       .execute())
            return self._handle_response(response, f"Delete user {google_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_user_by_email(self, email: str) -> DatabaseResponse:
        """
        Delete user by email
        
        Args:
            email: User email to delete
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('email', email)
                       .execute())
            return self._handle_response(response, f"Delete user with email {email}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_old_records(self, days_old: int = 30) -> DatabaseResponse:
        """
        Delete records older than specified days
        
        Args:
            days_old: Number of days old to consider for deletion
        """
        try:
            cutoff_date = datetime.utcnow().replace(microsecond=0)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_old)
            
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .lt('created_at', cutoff_date.isoformat())
                       .execute())
            return self._handle_response(response, f"Delete records older than {days_old} days")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # REALTIME SUBSCRIPTIONS (Note: Python supabase client has different realtime implementation)
    
    def setup_realtime_listener(self, callback: Callable, event_type: str = '*'):
        """
        Set up realtime listener for table changes
        
        Args:
            callback: Function to call when changes occur
            event_type: Type of event to listen for ('INSERT', 'UPDATE', 'DELETE', '*')
        """
        try:
            def handle_change(payload):
                logger.info(f"Realtime change received: {payload}")
                callback(payload)
            
            # Note: Python Supabase realtime implementation may vary
            # This is a conceptual implementation
            channel = self.supabase.channel(f'google_auth_{event_type}_channel')
            
            if hasattr(channel, 'on'):
                channel.on('postgres_changes', {
                    'event': event_type,
                    'schema': 'public',
                    'table': self.table_name
                }, handle_change)
                
                channel.subscribe()
                logger.info(f"Realtime listener set up for {event_type} events")
                return channel
            else:
                logger.warning("Realtime functionality not available in this Python client version")
                return None
        except Exception as e:
            logger.error(f"Failed to set up realtime listener: {e}")
            return None
