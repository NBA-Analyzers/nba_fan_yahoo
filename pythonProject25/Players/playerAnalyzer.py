from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.endpoints import commonplayerinfo

from Players.player import Player


## for only single player
class PlayerAnalyzer:
    players_rename = {"Xavier Tillman Sr.": "Xavier Tillman", "P.J. Washington Jr.": "P.J. Washington"}

    def _rename_players(self, full_name):
        if full_name in PlayerAnalyzer.players_rename:
            full_name = PlayerAnalyzer.players_rename[full_name]

        return full_name
