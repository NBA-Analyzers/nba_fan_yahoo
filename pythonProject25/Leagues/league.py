class League(object):

    def __init__(self, league_info):
        self.league_key = league_info['league_key']
        self.league_name = league_info['name']
        self.num_teams = league_info['num_teams']

    def __len__(self):
        return self.num_teams
