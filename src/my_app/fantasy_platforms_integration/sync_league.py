from typing import Protocol

class SyncLeagueData(Protocol):
    """Interface that all platform syncs must implement"""
    
    def league_setting(self):
        """Get league settings and configuration"""
        ...

    def standings(self):
        """Get current league standings"""
        ...
    
    def matchups(self,start_week,end_week):
        """Get matchup data for all weeks"""
        ...
    
    def free_agents(self):
        """Get available free agents"""
        ...
    
    def daily_roster(self):
        """Get daily roster setup"""
        ...

    def team_current_roster(self):
        "Get all teams current roster"
        ...
    
    