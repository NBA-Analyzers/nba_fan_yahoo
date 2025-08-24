from typing import List, Optional
from models.google_fantasy import GoogleFantasy
from repositories.google_fantasy_repository import GoogleFantasyRepository
from repositories.google_auth_repository import GoogleAuthRepository
from repositories.yahoo_auth_repository import YahooAuthRepository
from exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

class FantasyService:
    def __init__(self):
        self.google_fantasy_repo = GoogleFantasyRepository()
        self.google_auth_repo = GoogleAuthRepository()
        self.yahoo_auth_repo = YahooAuthRepository()
    
    def connect_fantasy_platform(self, google_fantasy: GoogleFantasy) -> GoogleFantasy:
        """Connect a Google user to a fantasy platform"""
        # Validate that Google user exists
        google_user = self.google_auth_repo.get_by_google_user_id(google_fantasy.google_user_id)
        if not google_user:
            raise ValidationError("Google user does not exist")
        
        # For Yahoo platform, validate that Yahoo user exists
        if google_fantasy.fantasy_platform.lower() == "yahoo":
            yahoo_user = self.yahoo_auth_repo.get_by_yahoo_user_id(google_fantasy.fantasy_user_id)
            if not yahoo_user:
                raise ValidationError("Yahoo user does not exist")
        
        # Check if connection already exists
        existing_connection = self.google_fantasy_repo.get_by_google_and_platform(
            google_fantasy.google_user_id,
            google_fantasy.fantasy_platform
        )
        
        if existing_connection:
            raise DuplicateError("User already connected to this platform")
        
        # Create the connection
        created_data = self.google_fantasy_repo.create(google_fantasy.to_dict())
        return GoogleFantasy.from_dict(created_data)
    
    def get_user_fantasy_connections(self, google_user_id: str) -> List[GoogleFantasy]:
        """Get all fantasy platform connections for a Google user"""
        connections_data = self.google_fantasy_repo.get_by_google_user_id(google_user_id)
        return [GoogleFantasy.from_dict(data) for data in connections_data]
    
    def get_fantasy_connection(self, google_user_id: str, platform: str) -> Optional[GoogleFantasy]:
        """Get specific fantasy platform connection for a user"""
        connection_data = self.google_fantasy_repo.get_by_google_and_platform(google_user_id, platform)
        return GoogleFantasy.from_dict(connection_data) if connection_data else None
    
    def disconnect_fantasy_platform(self, google_user_id: str, platform: str) -> bool:
        """Disconnect user from a fantasy platform"""
        existing_connection = self.google_fantasy_repo.get_by_google_and_platform(google_user_id, platform)
        if not existing_connection:
            raise NotFoundError("Connection to this platform does not exist")
        
        return self.google_fantasy_repo.delete_by_google_and_platform(google_user_id, platform)
    
    def get_yahoo_user_id_for_google_user(self, google_user_id: str) -> Optional[str]:
        """Get Yahoo user ID for a Google user (helper method)"""
        yahoo_connection = self.get_fantasy_connection(google_user_id, "yahoo")
        return yahoo_connection.fantasy_user_id if yahoo_connection else None