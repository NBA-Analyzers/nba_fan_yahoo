from dataclasses import dataclass


@dataclass()
class Team(object):
    def __init__(self, league_id, team_info):
        self.league_id = league_id
        self.team_key = team_info['team_key']
        self.team_name = team_info['name']


