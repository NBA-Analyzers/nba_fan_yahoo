"""
Yahoo League Supabase Database Operations - Python Implementation
Handles Yahoo Fantasy League information for each user account
"""

import os
from typing import Dict, List, Optional, Union, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from supabase import create_client, Client
from postgrest.exceptions import APIError
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class YahooLeague:
    """Data class for Yahoo League structure"""
    yahoo_user_id: str
    league_id: str
    team_name: str
    created_at: Optional[str] = None

@dataclass
class DatabaseResponse:
    """Standardized response for database operations"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    count: Optional[int] = None

class YahooLeagueManager:
    """Manager class for Yahoo League table operations"""
    
    def __init__(self, url: str = None, key: str = None):
        """
        Initialize Supabase client for Yahoo League operations
        
        Args:
            url: Supabase project URL
            key: Supabase anon key
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_KEY')
        self.table_name = 'yahoo_league'
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY must be provided or set as environment variables")
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
            logger.info("Yahoo League Supabase client initialized successfully")
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
        Read all rows from yahoo_league table
        Equivalent to: supabase.from('yahoo_league').select('*')
        """
        try:
            response = self.supabase.table(self.table_name).select("*").execute()
            return self._handle_response(response, "Read all Yahoo league records")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def read_specific_columns(self, columns: List[str]) -> DatabaseResponse:
        """
        Read specific columns from yahoo_league table
        
        Args:
            columns: List of column names to select
            
        Equivalent to: supabase.from('yahoo_league').select('some_column,other_column')
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
            
        Equivalent to: supabase.from('yahoo_league').select('*').range(0, 9)
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
            Example: "yahoo_user_id, league_id, team_name, yahoo_auth(yahoo_username)"
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

    def get_leagues_by_user(self, yahoo_user_id: str) -> DatabaseResponse:
        """Get all leagues for a specific Yahoo user"""
        return self.filter_equal('yahoo_user_id', yahoo_user_id)

    def get_teams_in_league(self, league_id: str) -> DatabaseResponse:
        """Get all teams in a specific league"""
        return self.filter_equal('league_id', league_id)

    def get_user_team_in_league(self, yahoo_user_id: str, league_id: str) -> DatabaseResponse:
        """
        Get a specific user's team in a specific league
        
        Args:
            yahoo_user_id: Yahoo user ID
            league_id: League ID
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .select("*")
                       .eq('yahoo_user_id', yahoo_user_id)
                       .eq('league_id', league_id)
                       .execute())
            return self._handle_response(response, f"Get user {yahoo_user_id} team in league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def search_teams_by_name(self, team_name_pattern: str, case_sensitive: bool = False) -> DatabaseResponse:
        """
        Search teams by name pattern
        
        Args:
            team_name_pattern: Pattern to match (use % for wildcards)
            case_sensitive: Whether to use case-sensitive matching
        """
        return self.filter_like('team_name', f'%{team_name_pattern}%', case_sensitive)

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

    def get_multiple_users_leagues(self, yahoo_user_ids: List[str]) -> DatabaseResponse:
        """Get leagues for multiple users"""
        return self.filter_in_list('yahoo_user_id', yahoo_user_ids)

    def get_multiple_leagues(self, league_ids: List[str]) -> DatabaseResponse:
        """Get teams from multiple leagues"""
        return self.filter_in_list('league_id', league_ids)

    def filter_created_after(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get league memberships created after a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_greater_than('created_at', date)

    def filter_created_before(self, date: Union[str, datetime]) -> DatabaseResponse:
        """Get league memberships created before a specific date"""
        if isinstance(date, datetime):
            date = date.isoformat()
        return self.filter_less_than('created_at', date)

    def get_recent_league_joins(self, days: int = 7) -> DatabaseResponse:
        """Get users who joined leagues in the last N days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return self.filter_created_after(cutoff_date)

    def complex_filter(self, filters: Dict[str, Any]) -> DatabaseResponse:
        """
        Apply multiple filters
        
        Args:
            filters: Dictionary with filter conditions
            Example: {
                'team_name__ilike': '%champions%',
                'created_at__gt': '2024-01-01',
                'league_id__in': ['123', '456']
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
    
    def insert_single_row(self, league_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Insert a single row
        
        Args:
            league_data: Dictionary containing league data
            
        Equivalent to: supabase.from('yahoo_league').insert([{...}]).select()
        """
        try:
            # Add created_at if not provided
            if 'created_at' not in league_data:
                league_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert([league_data]).select().execute()
            return self._handle_response(response, "Insert Yahoo league record")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def add_user_to_league(self, yahoo_user_id: str, league_id: str, 
                          team_name: str) -> DatabaseResponse:
        """
        Add a user to a league with their team name
        
        Args:
            yahoo_user_id: Yahoo user ID
            league_id: League ID
            team_name: User's team name in the league
        """
        # Check if user is already in this league
        existing_membership = self.get_user_team_in_league(yahoo_user_id, league_id)
        if existing_membership.success and existing_membership.count > 0:
            return DatabaseResponse(
                success=False,
                error=f"User {yahoo_user_id} is already in league {league_id}",
                data=existing_membership.data
            )
        
        league_data = {
            'yahoo_user_id': yahoo_user_id,
            'league_id': league_id,
            'team_name': team_name,
            'created_at': datetime.utcnow().isoformat()
        }
        
        return self.insert_single_row(league_data)

    def insert_multiple_rows(self, leagues_data: List[Dict[str, Any]]) -> DatabaseResponse:
        """
        Insert multiple rows
        
        Args:
            leagues_data: List of league data dictionaries
            
        Equivalent to: supabase.from('yahoo_league').insert([{...}, {...}]).select()
        """
        try:
            # Add created_at to each record if not provided
            for league_data in leagues_data:
                if 'created_at' not in league_data:
                    league_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).insert(leagues_data).select().execute()
            return self._handle_response(response, f"Insert {len(leagues_data)} Yahoo league records")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def bulk_add_user_to_leagues(self, yahoo_user_id: str, 
                                leagues_info: List[Dict[str, str]]) -> DatabaseResponse:
        """
        Add a user to multiple leagues at once
        
        Args:
            yahoo_user_id: Yahoo user ID
            leagues_info: List of dictionaries with 'league_id' and 'team_name'
                         Example: [{'league_id': '123', 'team_name': 'My Team'}, ...]
        """
        leagues_data = []
        for league_info in leagues_info:
            leagues_data.append({
                'yahoo_user_id': yahoo_user_id,
                'league_id': league_info['league_id'],
                'team_name': league_info['team_name']
            })
        
        return self.insert_multiple_rows(leagues_data)

    def upsert_league_membership(self, league_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Upsert (insert or update) a league membership
        
        Args:
            league_data: League data dictionary
            
        Equivalent to: supabase.from('yahoo_league').upsert({...}).select()
        """
        try:
            if 'created_at' not in league_data:
                league_data['created_at'] = datetime.utcnow().isoformat()
            
            response = self.supabase.table(self.table_name).upsert(league_data).select().execute()
            return self._handle_response(response, "Upsert league membership")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # UPDATE OPERATIONS
    
    def update_team_name(self, yahoo_user_id: str, league_id: str, 
                        new_team_name: str) -> DatabaseResponse:
        """
        Update team name for a user in a specific league
        
        Args:
            yahoo_user_id: Yahoo user ID
            league_id: League ID
            new_team_name: New team name
            
        Equivalent to: supabase.from('yahoo_league').update({...}).eq(...).eq(...).select()
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update({'team_name': new_team_name})
                       .eq('yahoo_user_id', yahoo_user_id)
                       .eq('league_id', league_id)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update team name for user {yahoo_user_id} in league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def update_league_membership(self, yahoo_user_id: str, league_id: str, 
                                update_data: Dict[str, Any]) -> DatabaseResponse:
        """
        Update league membership data
        
        Args:
            yahoo_user_id: Yahoo user ID
            league_id: League ID
            update_data: Data to update
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .update(update_data)
                       .eq('yahoo_user_id', yahoo_user_id)
                       .eq('league_id', league_id)
                       .select()
                       .execute())
            return self._handle_response(response, f"Update membership for user {yahoo_user_id} in league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def bulk_update_team_names(self, yahoo_user_id: str, 
                              team_updates: Dict[str, str]) -> DatabaseResponse:
        """
        Update team names for a user across multiple leagues
        
        Args:
            yahoo_user_id: Yahoo user ID
            team_updates: Dictionary mapping league_id to new team_name
                         Example: {'league123': 'New Team Name', 'league456': 'Another Team'}
        """
        results = []
        for league_id, new_team_name in team_updates.items():
            result = self.update_team_name(yahoo_user_id, league_id, new_team_name)
            results.append(result)
        
        # Return summary of results
        successful_updates = sum(1 for r in results if r.success)
        return DatabaseResponse(
            success=successful_updates == len(results),
            data={
                'total_updates': len(results),
                'successful_updates': successful_updates,
                'failed_updates': len(results) - successful_updates
            },
            count=successful_updates
        )

    # DELETE OPERATIONS
    
    def remove_user_from_league(self, yahoo_user_id: str, league_id: str) -> DatabaseResponse:
        """
        Remove a user from a specific league
        
        Args:
            yahoo_user_id: Yahoo user ID
            league_id: League ID to remove user from
            
        Equivalent to: supabase.from('yahoo_league').delete().eq(...).eq(...)
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('yahoo_user_id', yahoo_user_id)
                       .eq('league_id', league_id)
                       .execute())
            return self._handle_response(response, f"Remove user {yahoo_user_id} from league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def remove_user_from_all_leagues(self, yahoo_user_id: str) -> DatabaseResponse:
        """
        Remove a user from all their leagues
        
        Args:
            yahoo_user_id: Yahoo user ID
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('yahoo_user_id', yahoo_user_id)
                       .execute())
            return self._handle_response(response, f"Remove user {yahoo_user_id} from all leagues")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_entire_league(self, league_id: str) -> DatabaseResponse:
        """
        Delete all teams/users from a specific league
        
        Args:
            league_id: League ID to delete
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('league_id', league_id)
                       .execute())
            return self._handle_response(response, f"Delete entire league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def bulk_remove_users_from_league(self, league_id: str, 
                                     yahoo_user_ids: List[str]) -> DatabaseResponse:
        """
        Remove multiple users from a specific league
        
        Args:
            league_id: League ID
            yahoo_user_ids: List of Yahoo user IDs to remove
        """
        try:
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .eq('league_id', league_id)
                       .in_('yahoo_user_id', yahoo_user_ids)
                       .execute())
            return self._handle_response(response, f"Bulk remove {len(yahoo_user_ids)} users from league {league_id}")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    def delete_old_league_memberships(self, days_old: int = 365) -> DatabaseResponse:
        """
        Delete league memberships older than specified days
        
        Args:
            days_old: Number of days old to consider for deletion
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            response = (self.supabase.table(self.table_name)
                       .delete()
                       .lt('created_at', cutoff_date.isoformat())
                       .execute())
            return self._handle_response(response, f"Delete memberships older than {days_old} days")
        except Exception as e:
            return DatabaseResponse(success=False, error=str(e))

    # ANALYTICS AND REPORTING
    
    def get_user_league_count(self, yahoo_user_id: str) -> DatabaseResponse:
        """Get the number of leagues a user is in"""
        user_leagues = self.get_leagues_by_user(yahoo_user_id)
        if user_leagues.success:
            return DatabaseResponse(
                success=True,
                data={'user_id': yahoo_user_id, 'league_count': user_leagues.count},
                count=user_leagues.count
            )
        return user_leagues

    def get_league_size(self, league_id: str) -> DatabaseResponse:
        """Get the number of teams in a league"""
        league_teams = self.get_teams_in_league(league_id)
        if league_teams.success:
            return DatabaseResponse(
                success=True,
                data={'league_id': league_id, 'team_count': league_teams.count},
                count=league_teams.count
            )
        return league_teams

    def get_league_statistics(self) -> DatabaseResponse:
        """Get comprehensive league statistics"""
        all_memberships = self.read_all_rows()
        if all_memberships.success:
            # Calculate statistics
            users_per_league = defaultdict(int)
            leagues_per_user = defaultdict(int)
            
            for membership in all_memberships.data:
                league_id = membership.get('league_id')
                yahoo_user_id = membership.get('yahoo_user_id')
                
                users_per_league[league_id] += 1
                leagues_per_user[yahoo_user_id] += 1
            
            stats = {
                'total_memberships': all_memberships.count,
                'unique_leagues': len(users_per_league),
                'unique_users': len(leagues_per_user),
                'average_users_per_league': sum(users_per_league.values()) / len(users_per_league) if users_per_league else 0,
                'average_leagues_per_user': sum(leagues_per_user.values()) / len(leagues_per_user) if leagues_per_user else 0,
                'largest_league_size': max(users_per_league.values()) if users_per_league else 0,
                'most_active_user_leagues': max(leagues_per_user.values()) if leagues_per_user else 0
            }
            
            return DatabaseResponse(
                success=True,
                data=stats,
                count=len(stats)
            )
        return all_memberships

    def get_most_popular_team_names(self, limit: int = 10) -> DatabaseResponse:
        """Get the most popular team names across all leagues"""
        all_teams = self.read_specific_columns(['team_name'])
        if all_teams.success:
            team_counts = defaultdict(int)
            for team in all_teams.data:
                team_name = team.get('team_name', '').strip().lower()
                if team_name:
                    team_counts[team_name] += 1
            
            # Sort by count and get top N
            popular_teams = sorted(team_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            return DatabaseResponse(
                success=True,
                data=[{'team_name': name, 'count': count} for name, count in popular_teams],
                count=len(popular_teams)
            )
        return all_teams

    def find_users_in_multiple_leagues(self, min_leagues: int = 2) -> DatabaseResponse:
        """Find users who are in multiple leagues"""
        all_memberships = self.read_all_rows()
        if all_memberships.success:
            user_league_counts = defaultdict(list)
            
            for membership in all_memberships.data:
                yahoo_user_id = membership.get('yahoo_user_id')
                league_id = membership.get('league_id')
                user_league_counts[yahoo_user_id].append(league_id)
            
            # Filter users with multiple leagues
            multi_league_users = [
                {'yahoo_user_id': user_id, 'leagues': leagues, 'league_count': len(leagues)}
                for user_id, leagues in user_league_counts.items()
                if len(leagues) >= min_leagues
            ]
            
            return DatabaseResponse(
                success=True,
                data=multi_league_users,
                count=len(multi_league_users)
            )
        return all_memberships

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
                logger.info(f"Yahoo league change received: {payload}")
                callback(payload)
            
            channel = self.supabase.channel(f'yahoo_league_{event_type}_channel')
            
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
