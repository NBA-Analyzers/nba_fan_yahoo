from abc import ABC, abstractmethod

class SyncLeagueData(ABC):
    """Interface that all platform syncs must implement"""
    
    
    @abstractmethod
    def league_setting(self):
        """Get league settings and configuration"""
        pass
    
    @abstractmethod
    def standings(self):
        """Get current league standings"""
        pass
    
    @abstractmethod
    def matchups(self,start_week,end_week):
        """Get matchup data for all weeks"""
        pass
    
    @abstractmethod
    def free_agents(self):
        """Get available free agents"""
        pass
    
    @abstractmethod
    def daily_roster(self):
        """Get daily roster setup"""
        pass 

    @abstractmethod
    def team_current_roster(self):
        "Get all teams current roster"
        pass