from abc import ABC, abstractmethod
from typing import Dict, Any

class SyncLeagueData(ABC):
    """Abstract base class that all platform syncs must implement"""
    
    @abstractmethod
    def _league_setting(self) -> None:
        """Get league settings and configuration"""
        pass

    @abstractmethod
    def _standings(self) -> None:
        """Get current league standings"""
        pass
    
    @abstractmethod
    def _matchups(self, start_week: int, end_week: int) -> None:
        """Get matchup data for all weeks"""
        pass
    
    @abstractmethod
    def _free_agents(self, position: str = 'Util') -> Dict[str, Any]:
        """Get available free agents"""
        pass
    
    @abstractmethod
    def _daily_roster(self, start_date: str, end_date: str, delay_seconds: float = 0.5) -> Dict[str, Any]:
        """Get daily roster setup"""
        pass

    @abstractmethod
    def _team_current_roster(self) -> Dict[str, Any]:
        """Get all teams current roster"""
        pass
    
    @abstractmethod
    def sync_full_league(self, start_week: int = 1, end_week: int = 20, days_back: int = 7) -> Dict[str, str]:
        """Sync all league data and save to JSON files"""
        pass
    
    