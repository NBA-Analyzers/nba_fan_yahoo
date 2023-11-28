from dataclasses import dataclass


@dataclass()
class Player(object):

    def __init__(self, player_name, player_id, stats=None):
        self.player_name: str = player_name
        self.player_id = player_id
        self.stats = stats
        # TODO nba_team
