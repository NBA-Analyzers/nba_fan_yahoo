
from typing import List, Optional
from models.yahoo_league import YahooLeague
from repositories.yahoo_league_repository import YahooLeagueRepository
from repositories.yahoo_auth_repository import YahooAuthRepository
from .fantasy_services import FantasyService
from exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

class LeagueService:
    def __init__(self):
        self.yahoo_league_repo = YahooLeagueRepository()
        self.yahoo_auth_repo = YahooAuthRepository()
        self.fantasy_service = FantasyService()
    
    def create_yahoo_league(self, yahoo_league: YahooLeague) -> YahooLeague:
        """Create a new Yahoo league"""
        # Validate that Yahoo user exists
        yahoo_user = self.yahoo_auth_repo.get_by_yahoo_user_id(yahoo_league.yahoo_user_id)
        if not yahoo_user:
            raise ValidationError("Yahoo user does not exist")
        
        # Check if league already exists
        existing_league = self.yahoo_league_repo.get_by_league_id(yahoo_league.league_id)
        if existing_league:
            raise DuplicateError("League already exists")
        
        created_data = self.yahoo_league_repo.create(yahoo_league.to_dict())
        return YahooLeague.from_dict(created_data)
    
    def get_yahoo_leagues_by_user(self, yahoo_user_id: str) -> List[YahooLeague]:
        """Get all leagues for a Yahoo user"""
        leagues_data = self.yahoo_league_repo.get_by_yahoo_user_id(yahoo_user_id)
        return [YahooLeague.from_dict(data) for data in leagues_data]
    
    def get_yahoo_leagues_by_google_user(self, google_user_id: str) -> List[YahooLeague]:
        """Get all Yahoo leagues for a Google user (through connection)"""
        yahoo_user_id = self.fantasy_service.get_yahoo_user_id_for_google_user(google_user_id)
        if not yahoo_user_id:
            return []
        
        return self.get_yahoo_leagues_by_user(yahoo_user_id)
    
    def get_league_by_id(self, league_id: str) -> YahooLeague:
        """Get a specific league by ID"""
        league_data = self.yahoo_league_repo.get_by_league_id(league_id)
        if not league_data:
            raise NotFoundError(f"League with id {league_id} not found")
        return YahooLeague.from_dict(league_data)
    
    def update_league(self, league_id: str, updates: dict) -> YahooLeague:
        """Update a league"""
        existing_league = self.yahoo_league_repo.get_by_league_id(league_id)
        if not existing_league:
            raise NotFoundError(f"League with id {league_id} not found")
        
        updated_data = self.yahoo_league_repo.update_by_league_id(league_id, updates)
        return YahooLeague.from_dict(updated_data)
    
    def delete_league(self, league_id: str) -> bool:
        """Delete a league"""
        existing_league = self.yahoo_league_repo.get_by_league_id(league_id)
        if not existing_league:
            raise NotFoundError(f"League with id {league_id} not found")
        
        return self.yahoo_league_repo.delete_by_field("league_id", league_id)
    
    def delete_all_leagues_for_yahoo_user(self, yahoo_user_id: str) -> bool:
        """Delete all leagues for a Yahoo user"""
        return self.yahoo_league_repo.delete_by_yahoo_user_id(yahoo_user_id)