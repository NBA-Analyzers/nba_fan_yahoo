from dataclasses import dataclass
from YahooLeague import YahooLeague
from DataBase import DataBase as db
@dataclass()
class Team(object):
    def __init__(self, team_key, name, league_name,league_id, stats=None):
        self.team_key = team_key
        self.team_name = name
        self.league_name = league_name
        self.league_id = league_id
        self.stats = stats

