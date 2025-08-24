
from typing import List, Dict, Any, Optional
from database.base_repository import BaseRepository

class YahooLeagueRepository(BaseRepository):
    def __init__(self):
        super().__init__("yahoo_league")
    
    def get_by_yahoo_user_id(self, yahoo_user_id: str) -> List[Dict[str, Any]]:
        return self.get_multiple_by_field("yahoo_user_id", yahoo_user_id)
    
    def get_by_league_id(self, league_id: str) -> Optional[Dict[str, Any]]:
        return self.get_by_field("league_id", league_id)
    
    def delete_by_yahoo_user_id(self, yahoo_user_id: str) -> bool:
        return self.delete_by_field("yahoo_user_id", yahoo_user_id)
    
    def update_by_league_id(self, league_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_by_field("league_id", league_id, data)
