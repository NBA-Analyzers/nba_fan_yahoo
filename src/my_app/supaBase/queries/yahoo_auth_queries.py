"""
Yahoo Auth Supabase Database Operations - Python Implementation
Handles Yahoo authentication information and token management
"""

import os
from typing import Dict, List, Optional, Union, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class YahooAuthUser:
    """Data class for Yahoo Auth user structure"""
    yahoo_user_id: str

    access_token: str
    refresh_token: str
    created_at: Optional[str] = None

@dataclass
class DatabaseResponse:
    """Standardized response for database operations"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    count: Optional[int] = None

class YahooAuthManager:
    """Manager class for Yahoo Auth table operations"""
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase client for Yahoo Auth operations
        
        Args:
            url: Supabase project URL
            key: Supabase anon key
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_KEY')
        self.table_name = 'yahoo_auth'
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be provided or set as environment variables")
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
            logger.info("Yahoo Auth Supabase client initialized successfully")
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
        Read all rows from yahoo_auth table
        Equivalent to: supabase.from('yahoo_auth').select('*')
        """
        try:
            response = self.supabase.table(self.table_name).select("*").execute()
            return self._handle_response(response, "Read all Yahoo auth records")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_specific_columns(self, columns: List[str]) -> DatabaseResponse:
        """
        Read specific columns from yahoo_auth table
        
        Args:
            columns: List of column names to select
            
        Equivalent to: supabase.from('yahoo_auth').select('some_column,other_column')
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
            
        Equivalent to: supabase.from('yahoo_auth').select('*').range(0, 9)
        """
        try:
            response = self.supabase.table(self.table_name).select("*").range(start, end).execute()
            return self._handle_response(response, f"Read with pagination ({start}-{end})")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_with_referenced_tables(self, reference_query: str) -> DatabaseResponse:
        """
        Read with referenced tables (joins)
        
        Args:
            reference_query: Query string for referenced tables
            Example: "yahoo_user_id, users(email, full_name)"
        """
        try:
            response = self.supabase.table(self.table_name).select(reference_query).execute()
            return self._handle_response(response, f"Read with references: {reference_query}")
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

    def get_by_yahoo_user_id(self, yahoo_user_id: str) -> DatabaseResponse:
        """Get Yahoo auth info by Yahoo user ID"""
        return self.filter_equal('yahoo_user_id', yahoo_user_id)


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

    def get_multiple_users(self, yahoo_user_ids: List[str]) -> DatabaseResponse:
        """Get multiple users by their Yahoo user IDs"""
        return self.filter_in_list('yahoo_user_id', yahoo_user_ids)

    def filter_is_null(self, column: str) -> DatabaseResponse:
        """Filter rows where column is NULL"""
        try:
            response = self.supabase.table(self.table_name).select("*").is_(column, None).execute()
            return self._handle_response(response, f"Filter {column} IS NULL")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def find_missing_tokens(self) -> DatabaseResponse:
        """Find records with missing access or refresh tokens"""
        try:
            query = self.supabase.table(self.table_name).select("*")
            response = query.or_("access_token.is.null,refresh_token.is.null").execute()
            return self._handle_response(response, "Find missing tokens")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def filter_created_after(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get users created after a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_greater_than('created_at', date)

    def filter_created_before(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get users created before a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_less_than('created_at', date)

    def get_recent_users(self, days: int = 7) -> DatabaseResponse:
        """Get users created in the last N days"""
        cutoff_date = datetime.now(datetime.timezone.utc) - timedelta(days=days)
        return self.filter_created_after(cutoff_date)


    # INSERT OPERATIONS
    
    def insert_single_row(self, user_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Insert a single row
        
        Args:
            user_data: Dictionary containing user data
            
        Equivalent to: supabase.from('yahoo_auth').insert([{...}]).select()
        """
        try:
            # Add created_at if not provided
            if 'created_at' not in user_data:
                user_data['created_at'] = datetime.now().isoformat()
            
            response = self.supabase.table(self.table_name).insert([user_data]).select().execute()
            return self._handle_response(response, "Insert Yahoo auth record")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))



    def insert_multiple_rows(self, users_data: List[Dict[str, Any]]) -> DatabaseResponse:
        """
        Insert multiple rows
        
        Args:
            users_data: List of user data dictionaries
            
        Equivalent to: supabase.from('yahoo_auth').insert([{...}, {...}]).select()
        """
        try:
            # Add created_at to each record if not provided
            for user_data in users_data:
                if 'created_at' not in user_data:
                    user_data['created_at'] = datetime.now(datetime.timezone.utc).isoformat()
            
            response = self.supabase.table(self.table_name).insert(users_data).select().execute()
            return self._handle_response(response, f"Insert {len(users_data)} Yahoo auth records")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def upsert_user(self, user_data: Dict[str, Any], 
                   conflict_column: str = 'yahoo_user_id') -> DatabaseResponse:
        """
        Upsert (insert or update) a Yahoo user
        
        Args:
            user_data: User data dictionary
            conflict_column: Column to check for conflicts
            
        Equivalent to: supabase.from('yahoo_auth').upsert({...}).select()
        """
        try:
            if 'created_at' not in user_data:
                user_data['created_at'] = datetime.now(datetime.timezone.utc).isoformat()
            
            response = self.supabase.table(self.table_name).upsert(user_data).select().execute()
            return self._handle_response(response, "Upsert Yahoo user")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # UPDATE OPERATIONS
    
    def update_user_by_id(self, yahoo_user_id: str, 
                         update_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Update user by Yahoo user ID
        
        Args:
            yahoo_user_id: Yahoo user ID to update
            update_data: Data to update
            
        Equivalent to: supabase.from('yahoo_auth').update({...}).eq('yahoo_user_id', id).select()
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update(update_data)
                       .eq('yahoo_user_id', yahoo_user_id)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update Yahoo user {yahoo_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))
    def update_tokens(self, yahoo_user_id: str, access_token: str, 
                     refresh_token: str = None) -> DatabaseResponse:
        """
        Update access and/or refresh tokens for a user
        
        Args:
            yahoo_user_id: Yahoo user ID
            access_token: New access token
            refresh_token: New refresh token (optional)
        """
        update_data = {'access_token': access_token}
        if refresh_token:
            update_data['refresh_token'] = refresh_token
        
        return self.update_user_by_id(yahoo_user_id, update_data)

    def update_access_token(self, yahoo_user_id: str, new_token: str) -> DatabaseResponse:
        """
        Update only the access token for a specific user
        
        Args:
            yahoo_user_id: Yahoo user ID
            new_token: New access token
        """
        return self.update_user_by_id(yahoo_user_id, {'access_token': new_token})

    def update_refresh_token(self, yahoo_user_id: str, new_token: str) -> DatabaseResponse:
        """
        Update only the refresh token for a specific user
        
        Args:
            yahoo_user_id: Yahoo user ID
            new_token: New refresh token
        """
        return self.update_user_by_id(yahoo_user_id, {'refresh_token': new_token})

    # DELETE OPERATIONS
    
    def delete_user_by_id(self, yahoo_user_id: str) -> DatabaseResponse:
        """
        Delete user by Yahoo user ID
        
        Args:
            yahoo_user_id: Yahoo user ID to delete
            
        Equivalent to: supabase.from('yahoo_auth').delete().eq('yahoo_user_id', id)
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('yahoo_user_id', yahoo_user_id)
                       .execute())
            return self._handle_response(response, f"Delete Yahoo user {yahoo_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_users_with_invalid_tokens(self) -> DatabaseResponse:
        """
        Delete users with missing or null tokens
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .or_("access_token.is.null,refresh_token.is.null")
                       .execute())
            return self._handle_response(response, "Delete users with invalid tokens")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_old_records(self, days_old: int = 365) -> DatabaseResponse:
        """
        Delete records older than specified days
        
        Args:
            days_old: Number of days old to consider for deletion
        """
        try:
            cutoff_date = datetime.now(datetime.timezone.utc) - timedelta(days=days_old)
            
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .lt('created_at', cutoff_date.isoformat())
                       .execute())
            return self._handle_response(response, f"Delete records older than {days_old} days")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def bulk_delete_users(self, yahoo_user_ids: List[str]) -> DatabaseResponse:
        """
        Delete multiple users by their Yahoo user IDs
        
        Args:
            yahoo_user_ids: List of Yahoo user IDs to delete
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .in_('yahoo_user_id', yahoo_user_ids)
                       .execute())
            return self._handle_response(response, f"Bulk delete {len(yahoo_user_ids)} users")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # TOKEN MANAGEMENT UTILITIES
    
    def get_user_tokens(self, yahoo_user_id: str) -> DatabaseResponse:
        """
        Get only the tokens for a specific user
        
        Args:
            yahoo_user_id: Yahoo user ID
        """
        return self.read_specific_columns(['yahoo_user_id', 'access_token', 'refresh_token'])

    def refresh_user_session(self, yahoo_user_id: str, new_access_token: str, 
                            new_refresh_token: str = None) -> DatabaseResponse:
        """
        Refresh user session with new tokens
        
        Args:
            yahoo_user_id: Yahoo user ID
            new_access_token: New access token
            new_refresh_token: New refresh token (optional)
        """
        logger.info(f"Refreshing session for Yahoo user {yahoo_user_id}")
        return self.update_tokens(yahoo_user_id, new_access_token, new_refresh_token)

    def validate_user_exists(self, yahoo_user_id: str) -> bool:
        """
        Check if a Yahoo user exists in the database
        
        Args:
            yahoo_user_id: Yahoo user ID to check
            
        Returns:
            bool: True if user exists, False otherwise
        """
        result = self.get_by_yahoo_user_id(yahoo_user_id)
        return result.success and result.count > 0

    # ANALYTICS AND REPORTING
    
    def get_user_count(self) -> DatabaseResponse:
        """Get total count of Yahoo users"""
        all_users = self.read_all_rows()
        if all_users.success:
            return DatabaseResponse(
                success=True,
                count=all_users.count,
                data={'total_users': all_users.count}
            )
        return all_users

    def get_users_by_date_range(self, start_date: Union[str, datetime], 
                               end_date: Union[str, datetime]) -> DatabaseResponse:
        """
        Get users created within a specific date range
        
        Args:
            start_date: Start date
            end_date: End date
        """
        if isinstance(start_date, datetime):
            start_date = start_date.isoformat()
        if isinstance(end_date, datetime):
            end_date = end_date.isoformat()
        
        return self.complex_filter({
            'created_at__gte': start_date,
            'created_at__lte': end_date
        })

    # REALTIME SUBSCRIPTIONS
    
    def setup_realtime_listener(self, callback: Callable, event_type: str = '*'):
        """
        Set up realtime listener for table changes
        
        Args:
            callback: Function to call when changes occur
            event_type: Type of event to listen for ('INSERT', 'UPDATE', 'DELETE', '*')
        """
        try:
            def handle_change(payload):
                logger.info(f"Yahoo auth change received: {payload}")
                callback(payload)
            
            channel = self.supabase.channel(f'yahoo_auth_{event_type}_channel')
            
            if hasattr(channel, 'on'):
                channel.on('postgres_changes', {
                    'event': event_type,
                    'schema': 'public',
                    'table': self.table_name
                }, handle_change)
                
                channel.subscribe()
                logger.info(f"Realtime listener set up for {event_type} events on {self.table_name}")
                return channel
            else:
                logger.warning("Realtime functionality not available in this Python client version")
                return None
        except Exception as e:
            logger.error(f"Failed to set up realtime listener: {e}")
            return None
