from abc import ABC, abstractmethod
from typing import Any, Dict


class SyncLeagueData(ABC):
    """Abstract base class that all platform syncs must implement"""

    @abstractmethod
    def _league_setting(self) -> Any:
        """Get league settings and configuration"""

    @abstractmethod
    def _standings(self) -> Any:
        """Get current league standings"""

    @abstractmethod
    def _matchups(self, start_week: int, end_week: int) -> Any:
        """Get matchup data for all weeks"""

    @abstractmethod
    def _free_agents(self, position: str = 'Util') -> Dict[str, Any]:
        """Get available free agents"""

    @abstractmethod
    def _team_current_roster(self) -> Dict[str, Any]:
        """Get all teams current roster"""

    @abstractmethod
    def sync_full_league(self, blob_storage) -> Dict[str, Any]:
        """Sync all league data; returns {part name: data} for the parts that synced"""
