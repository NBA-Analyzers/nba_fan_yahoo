import inspect
from dataclasses import dataclass
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import players, teams


@dataclass()
class Player(object):

    def __init__(self, player_info):
        # self.__full_name = full_name
        # self.__id = player_info['id']
        #self.draft_year = player_info['DRAFT_YEAR'].iloc[0]
        self.first_name = player_info['first_name']
        self.last_name = player_info['last_name']
        self.full_name: str = player_info['full_name']
        self.id = player_info['id']

