# fantasy_services.py
from typing import List, Optional, Dict, Any
from ..models.google_fantasy import GoogleFantasy
from ..repositories.google_fantasy_repository import GoogleFantasyRepository
from ..repositories.google_auth_repository import GoogleAuthRepository
from ..repositories.yahoo_auth_repository import YahooAuthRepository
from ..exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError
from ..utils.validators import validate_user_id, validate_platform

class FantasyService:
    def __init__(self):
        self.google_fantasy_repo = GoogleFantasyRepository()
        self.google_auth_repo = GoogleAuthRepository()
        self.yahoo_auth_repo = YahooAuthRepository()
    
    def connect_fantasy_platform(self, google_fantasy: GoogleFantasy) -> GoogleFantasy:
        """Connect a Google user to a fantasy platform"""
        
        # Validate input data
        validate_user_id(google_fantasy.google_user_id, "Google")
        validate_user_id(google_fantasy.fantasy_user_id, "Fantasy")
        validate_platform(google_fantasy.fantasy_platform)
        
        # Validate that Google user exists
        google_user = self.google_auth_repo.get_by_google_user_id(google_fantasy.google_user_id)
        if not google_user:
            raise ValidationError(f"Google user '{google_fantasy.google_user_id}' does not exist")
        
        # For Yahoo platform, validate that Yahoo user exists
        if google_fantasy.fantasy_platform.lower() == "yahoo":
            yahoo_user = self.yahoo_auth_repo.get_by_yahoo_user_id(google_fantasy.fantasy_user_id)
            if not yahoo_user:
                raise ValidationError(f"Yahoo user '{google_fantasy.fantasy_user_id}' does not exist")
        
        # Check if exact connection already exists (composite key check)
        existing_connection = self.google_fantasy_repo.get_by_composite_key(
            google_fantasy.google_user_id,
            google_fantasy.fantasy_user_id,
            google_fantasy.fantasy_platform
        )
        
        if existing_connection:
            raise DuplicateError("This exact connection already exists")
        
        # Create the connection
        created_data = self.google_fantasy_repo.create(google_fantasy.to_dict())
        return GoogleFantasy.from_dict(created_data)
    
    def get_user_fantasy_connections(self, google_user_id: str) -> List[GoogleFantasy]:
        """Get all fantasy platform connections for a Google user"""
        validate_user_id(google_user_id, "Google")
        
        # Verify Google user exists
        if not self.google_auth_repo.get_by_google_user_id(google_user_id):
            raise NotFoundError(f"Google user '{google_user_id}' does not exist")
        
        connections_data = self.google_fantasy_repo.get_by_google_user_id(google_user_id)
        return [GoogleFantasy.from_dict(data) for data in connections_data]
    
    def get_fantasy_connection(self, google_user_id: str, platform: str) -> Optional[GoogleFantasy]:
        """Get specific fantasy platform connection for a user"""
        validate_user_id(google_user_id, "Google")
        validate_platform(platform)
        
        connection_data = self.google_fantasy_repo.get_by_google_and_platform(google_user_id, platform)
        return GoogleFantasy.from_dict(connection_data) if connection_data else None
    
    def disconnect_fantasy_platform(self, google_user_id: str, platform: str) -> bool:
        """Disconnect user from a fantasy platform (removes ALL connections to that platform)"""
        validate_user_id(google_user_id, "Google")
        validate_platform(platform)
        
        existing_connection = self.google_fantasy_repo.get_by_google_and_platform(google_user_id, platform)
        if not existing_connection:
            raise NotFoundError(f"No connection to '{platform}' platform exists for this user")
        
        return self.google_fantasy_repo.delete_by_google_and_platform(google_user_id, platform)
    
    def disconnect_specific_fantasy_connection(self, google_user_id: str, fantasy_user_id: str, platform: str) -> bool:
        """Disconnect a specific fantasy connection (by composite key)"""
        validate_user_id(google_user_id, "Google")
        validate_user_id(fantasy_user_id, "Fantasy")
        validate_platform(platform)
        
        existing_connection = self.google_fantasy_repo.get_by_composite_key(google_user_id, fantasy_user_id, platform)
        if not existing_connection:
            raise NotFoundError("This specific connection does not exist")
        
        return self.google_fantasy_repo.delete_by_composite_key(google_user_id, fantasy_user_id, platform)
    
    def get_yahoo_user_id_for_google_user(self, google_user_id: str) -> Optional[str]:
        """Get Yahoo user ID for a Google user (returns first found if multiple exist)"""
        validate_user_id(google_user_id, "Google")
        
        yahoo_connection = self.get_fantasy_connection(google_user_id, "yahoo")
        return yahoo_connection.fantasy_user_id if yahoo_connection else None
    
    def get_all_yahoo_user_ids_for_google_user(self, google_user_id: str) -> List[str]:
        """Get all Yahoo user IDs for a Google user"""
        validate_user_id(google_user_id, "Google")
        
        connections = self.get_user_fantasy_connections(google_user_id)
        yahoo_connections = [conn for conn in connections if conn.fantasy_platform.lower() == "yahoo"]
        return [conn.fantasy_user_id for conn in yahoo_connections]
    
    def get_google_users_for_yahoo_user(self, yahoo_user_id: str) -> List[Dict[str, Any]]:
        """Get all Google users connected to a specific Yahoo user"""
        validate_user_id(yahoo_user_id, "Yahoo")
        
        # Verify Yahoo user exists
        if not self.yahoo_auth_repo.get_by_yahoo_user_id(yahoo_user_id):
            raise NotFoundError(f"Yahoo user '{yahoo_user_id}' does not exist")
        
        connections_data = self.google_fantasy_repo.get_google_users_by_yahoo_user(yahoo_user_id)
        return [GoogleFantasy.from_dict(data) for data in connections_data]
    
    def is_google_user_connected_to_platform(self, google_user_id: str, platform: str) -> bool:
        """Check if Google user is connected to a specific platform"""
        validate_user_id(google_user_id, "Google")
        validate_platform(platform)
        
        connection = self.get_fantasy_connection(google_user_id, platform)
        return connection is not None
    
    def get_connection_count_for_google_user(self, google_user_id: str) -> int:
        """Get count of all fantasy platform connections for a Google user"""
        validate_user_id(google_user_id, "Google")
        
        connections = self.get_user_fantasy_connections(google_user_id)
        return len(connections)
    
    def get_platform_statistics(self) -> Dict[str, int]:
        """Get statistics about platform connections"""
        all_connections = self.google_fantasy_repo.get_all()
        
        stats = {}
        for connection in all_connections:
            platform = connection.get('fantasy_platform', '').lower()
            stats[platform] = stats.get(platform, 0) + 1
            
        return stats