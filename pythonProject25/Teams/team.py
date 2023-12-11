from dataclasses import dataclass
from YahooLeague import YahooLeague
from DataBase import DataBase as db


@dataclass()
class Team(object):
    def __init__(self, team_key, name, league_name, league_id, current_stats=None, last_stats=None):
        self.team_key = team_key
        self.team_name = name
        self.league_name = league_name
        self.league_id = league_id
        self.current_stats = current_stats
        self.last_stats = last_stats
        self.roster = None
        self.team_length = 0

