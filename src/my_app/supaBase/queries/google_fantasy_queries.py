"""
Google Fantasy Supabase Database Operations - Python Implementation
Handles linking Google users with fantasy platform accounts
"""

import os
from typing import Dict, List, Optional, Union, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class GoogleFantasyLink:
    """Data class for Google Fantasy link structure"""
    google_user_id: str
    fantasy_user_id: str
    fantasy_platform: str
    created_at: Optional[str] = None

@dataclass
class DatabaseResponse:
    """Standardized response for database operations"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    count: Optional[int] = None

class GoogleFantasyManager:
    """Manager class for Google Fantasy table operations"""
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase client for Google Fantasy operations
        
        Args:
            url: Supabase project URL
            key: Supabase anon key
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_KEY')
        self.table_name = 'google_fantasy'
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be provided or set as environment variables")
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
            logger.info("Google Fantasy Supabase client initialized successfully")
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
        Read all rows from google_fantasy table
        Equivalent to: supabase.from('google_fantasy').select('*')
        """
        try:
            response = self.supabase.table(self.table_name).select("*").execute()
            return self._handle_response(response, "Read all fantasy links")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_specific_columns(self, columns: List[str]) -> DatabaseResponse:
        """
        Read specific columns from google_fantasy table
        
        Args:
            columns: List of column names to select
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
            Example: "google_user_id, google_auth(full_name, email)"
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

    def get_by_google_user(self, google_user_id: str) -> DatabaseResponse:
        """Get all fantasy platform links for a Google user"""
        return self.filter_equal('google_user_id', google_user_id)

    def get_by_fantasy_platform(self, platform: str) -> DatabaseResponse:
        """Get all users linked to a specific fantasy platform"""
        return self.filter_equal('fantasy_platform', platform)

    def get_by_fantasy_user(self, fantasy_user_id: str, platform: str = None) -> DatabaseResponse:
        """
        Get Google user linked to a specific fantasy user
        
        Args:
            fantasy_user_id: Fantasy platform user ID
            platform: Optional platform name for more specific search
        """
        try:
            query = self.supabase.table(self.table_name).select("*").eq('fantasy_user_id', fantasy_user_id)
            if platform:
                query = query.eq('fantasy_platform', platform)
            response = query.execute()
            return self._handle_response(response, f"Get by fantasy user {fantasy_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def check_link_exists(self, google_user_id: str, fantasy_platform: str) -> DatabaseResponse:
        """
        Check if a link exists between Google user and fantasy platform
        
        Args:
            google_user_id: Google user ID
            fantasy_platform: Fantasy platform name
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .select("*")
                       .eq('google_user_id', google_user_id)
                       .eq('fantasy_platform', fantasy_platform)
                       .execute())
            return self._handle_response(response, f"Check link exists for {google_user_id} on {fantasy_platform}")
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

    def get_multiple_platforms(self, platforms: List[str]) -> DatabaseResponse:
        """Get all links for multiple fantasy platforms"""
        return self.filter_in_list('fantasy_platform', platforms)

    def filter_created_after(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get links created after a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_greater_than('created_at', date)

    def filter_created_before(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get links created before a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_less_than('created_at', date)

    def complex_filter(self, filters: Dict[str, Any]) -> DatabaseResponse:
        """
        Apply multiple filters
        
        Args:
            filters: Dictionary with filter conditions
            Example: {
                'fantasy_platform': 'yahoo',
                'google_user_id__like': 'google%',
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
    
    def insert_single_row(self, link_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Insert a single fantasy link
        
        Args:
            link_data: Dictionary containing link data
        """
        try:
            # Add created_at if not provided
            if 'created_at' not in link_data:
                link_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert([link_data]).select().execute()
            return self._handle_response(response, "Insert fantasy link")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def link_google_to_fantasy(self, google_user_id: str, fantasy_user_id: str, 
                              fantasy_platform: str) -> DatabaseResponse:
        """
        Link a Google user to a fantasy platform account
        
        Args:
            google_user_id: Google user ID
            fantasy_user_id: Fantasy platform user ID
            fantasy_platform: Name of the fantasy platform (e.g., 'yahoo', 'espn', 'sleeper')
        """
        # Check if link already exists
        existing_link = self.check_link_exists(google_user_id, fantasy_platform)
        if existing_link.success and existing_link.count > 0:
            return DatabaseResponse(
                success=False, 
                error=f"Link already exists between {google_user_id} and {fantasy_platform}",
                data=existing_link.data
            )
        
        link_data = {
            'google_user_id': google_user_id,
            'fantasy_user_id': fantasy_user_id,
            'fantasy_platform': fantasy_platform,
            'created_at': datetime.utcnow().isoformat()
        }
        
        return self.insert_single_row(link_data)

    def insert_multiple_rows(self, links_data: List[Dict[str, Any]]) -> DatabaseResponse:
        """
        Insert multiple fantasy links
        
        Args:
            links_data: List of link data dictionaries
        """
        try:
            # Add created_at to each record if not provided
            for link_data in links_data:
                if 'created_at' not in link_data:
                    link_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert(links_data).select().execute()
            return self._handle_response(response, f"Insert {len(links_data)} fantasy links")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def bulk_link_platforms(self, google_user_id: str, 
                           platform_accounts: Dict[str, str]) -> DatabaseResponse:
        """
        Link a Google user to multiple fantasy platforms at once
        
        Args:
            google_user_id: Google user ID
            platform_accounts: Dictionary mapping platform names to user IDs
                             Example: {'yahoo': 'yahoo123', 'espn': 'espn456'}
        """
        links_data = []
        for platform, fantasy_user_id in platform_accounts.items():
            links_data.append({
                'google_user_id': google_user_id,
                'fantasy_user_id': fantasy_user_id,
                'fantasy_platform': platform
            })
        
        return self.insert_multiple_rows(links_data)

    def upsert_link(self, link_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Upsert (insert or update) a fantasy link
        
        Args:
            link_data: Link data dictionary
        """
        try:
            if 'created_at' not in link_data:
                link_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).upsert(link_data).select().execute()
            return self._handle_response(response, "Upsert fantasy link")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # UPDATE OPERATIONS
    
    def update_fantasy_user_id(self, google_user_id: str, fantasy_platform: str, 
                              new_fantasy_user_id: str) -> DatabaseResponse:
        """
        Update the fantasy user ID for a specific Google user and platform
        
        Args:
            google_user_id: Google user ID
            fantasy_platform: Fantasy platform name
            new_fantasy_user_id: New fantasy user ID
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update({'fantasy_user_id': new_fantasy_user_id})
                       .eq('google_user_id', google_user_id)
                       .eq('fantasy_platform', fantasy_platform)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update fantasy user ID for {google_user_id} on {fantasy_platform}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def update_platform_name(self, google_user_id: str, old_platform: str, 
                            new_platform: str) -> DatabaseResponse:
        """
        Update the platform name for a specific link
        
        Args:
            google_user_id: Google user ID
            old_platform: Current platform name
            new_platform: New platform name
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update({'fantasy_platform': new_platform})
                       .eq('google_user_id', google_user_id)
                       .eq('fantasy_platform', old_platform)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update platform from {old_platform} to {new_platform}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # DELETE OPERATIONS
    
    def delete_link(self, google_user_id: str, fantasy_platform: str) -> DatabaseResponse:
        """
        Delete a specific link between Google user and fantasy platform
        
        Args:
            google_user_id: Google user ID
            fantasy_platform: Fantasy platform name
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('google_user_id', google_user_id)
                       .eq('fantasy_platform', fantasy_platform)
                       .execute())
            return self._handle_response(response, f"Delete link for {google_user_id} on {fantasy_platform}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_all_user_links(self, google_user_id: str) -> DatabaseResponse:
        """
        Delete all fantasy platform links for a Google user
        
        Args:
            google_user_id: Google user ID
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('google_user_id', google_user_id)
                       .execute())
            return self._handle_response(response, f"Delete all links for {google_user_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_platform_links(self, fantasy_platform: str) -> DatabaseResponse:
        """
        Delete all links to a specific fantasy platform
        
        Args:
            fantasy_platform: Fantasy platform name
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('fantasy_platform', fantasy_platform)
                       .execute())
            return self._handle_response(response, f"Delete all {fantasy_platform} links")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_old_links(self, days_old: int = 365) -> DatabaseResponse:
        """
        Delete links older than specified days
        
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
            return self._handle_response(response, f"Delete links older than {days_old} days")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # ANALYTICS AND REPORTING
    
    def get_user_platform_count(self, google_user_id: str) -> DatabaseResponse:
        """Get count of platforms linked to a specific Google user"""
        user_links = self.get_by_google_user(google_user_id)
        if user_links.success:
            return DatabaseResponse(
                success=True,
                data=user_links.data,
                count=user_links.count
            )
        return user_links

    def get_platform_statistics(self) -> DatabaseResponse:
        """Get statistics about platform usage"""
        all_links = self.read_all_rows()
        if all_links.success:
            platform_stats = {}
            for link in all_links.data:
                platform = link.get('fantasy_platform')
                platform_stats[platform] = platform_stats.get(platform, 0) + 1
            
            return DatabaseResponse(
                success=True,
                data=platform_stats,
                count=len(platform_stats)
            )
        return all_links

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
                logger.info(f"Fantasy link change received: {payload}")
                callback(payload)
            
            channel = self.supabase.channel(f'google_fantasy_{event_type}_channel')
            
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