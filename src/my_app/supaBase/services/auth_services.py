from typing import Optional
from models.google_auth import GoogleAuth
from models.yahoo_auth import YahooAuth
from repositories.google_auth_repository import GoogleAuthRepository
from repositories.yahoo_auth_repository import YahooAuthRepository
from exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

class AuthService:
    def __init__(self):
        self.google_auth_repo = GoogleAuthRepository()
        self.yahoo_auth_repo = YahooAuthRepository()
    
    # Google Authentication Methods
    def create_or_update_google_user(self, google_auth: GoogleAuth) -> GoogleAuth:
        """Create new Google user or update existing one"""
        existing_user = self.google_auth_repo.get_by_google_user_id(google_auth.google_user_id)
        
        if existing_user:
            # Update existing user
            updated_data = self.google_auth_repo.update_by_google_user_id(
                google_auth.google_user_id, 
                google_auth.to_dict()
            )
            return GoogleAuth.from_dict(updated_data)
        else:
            # Create new user
            created_data = self.google_auth_repo.create(google_auth.to_dict())
            return GoogleAuth.from_dict(created_data)
    
    def get_google_user(self, google_user_id: str) -> GoogleAuth:
        user_data = self.google_auth_repo.get_by_google_user_id(google_user_id)
        if not user_data:
            raise NotFoundError(f"Google user with id {google_user_id} not found")
        return GoogleAuth.from_dict(user_data)
    
    def get_google_user_by_email(self, email: str) -> Optional[GoogleAuth]:
        user_data = self.google_auth_repo.get_by_email(email)
        return GoogleAuth.from_dict(user_data) if user_data else None
    
    def update_google_user_tokens(self, google_user_id: str, access_token: str) -> GoogleAuth:
        existing_user = self.google_auth_repo.get_by_google_user_id(google_user_id)
        if not existing_user:
            raise NotFoundError(f"Google user with id {google_user_id} not found")
        
        updated_data = self.google_auth_repo.update_by_google_user_id(
            google_user_id, 
            {"access_token": access_token}
        )
        return GoogleAuth.from_dict(updated_data)
    
    # Yahoo Authentication Methods
    def create_or_update_yahoo_user(self, yahoo_auth: YahooAuth) -> YahooAuth:
        """Create new Yahoo user or update existing one"""
        existing_user = self.yahoo_auth_repo.get_by_yahoo_user_id(yahoo_auth.yahoo_user_id)
        
        if existing_user:
            # Update existing user
            updated_data = self.yahoo_auth_repo.update_by_yahoo_user_id(
                yahoo_auth.yahoo_user_id,
                yahoo_auth.to_dict()
            )
            return YahooAuth.from_dict(updated_data)
        else:
            # Create new user
            created_data = self.yahoo_auth_repo.create(yahoo_auth.to_dict())
            return YahooAuth.from_dict(created_data)
    
    def get_yahoo_user(self, yahoo_user_id: str) -> YahooAuth:
        user_data = self.yahoo_auth_repo.get_by_yahoo_user_id(yahoo_user_id)
        if not user_data:
            raise NotFoundError(f"Yahoo user with id {yahoo_user_id} not found")
        return YahooAuth.from_dict(user_data)
    
    def update_yahoo_tokens(self, yahoo_user_id: str, access_token: str, refresh_token: str) -> YahooAuth:
        existing_user = self.yahoo_auth_repo.get_by_yahoo_user_id(yahoo_user_id)
        if not existing_user:
            raise NotFoundError(f"Yahoo user with id {yahoo_user_id} not found")
        
        updated_data = self.yahoo_auth_repo.update_by_yahoo_user_id(
            yahoo_user_id,
            {"access_token": access_token, "refresh_token": refresh_token}
        )
        return YahooAuth.from_dict(updated_data)