from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import pyodbc


class YahooLeague:

    # cur_lg is the league number but in string
    def __init__(self, cur_lg):
        # connect to yahoo api

        sc = OAuth2(None, None, from_file='oauth22.json')
        # get game object
        self.gm = yfa.Game(sc, 'nba')
        self.cur_lg = cur_lg
        self.lg = self.gm.to_league('428.l.' + self.cur_lg)
        self.teames_in_league = self.lg.teams()
        ## get team roster by team_key
        self.get_team_roster_by_team_key = "select player_name from dbo.team_player where team_key =?"
        self.teams_by_league = "select team_name from dbo.league_teams where league_id = ?"
        self.teams_by_league = "select team_key from dbo.league_teams where league_id = ?"
        connection = pyodbc.connect('Driver={SQL Server};'
                                    'Server=PC-URI;'
                                    'Database=NBA_API;'
                                    'Trusted_Connection=yes;')
        self.cursor = connection.cursor()

    def teams_league(self):
        self.cursor.execute(self.teams_by_league, ('428.l.'+self.cur_lg,))
        all_teams = self.cursor.fetchall()
        final_teams = ''
        for i in all_teams:
            final_teams+=i[0]+'\n'
        return final_teams

    def __len__(self):
        return len(self.teams_league().split("\n"))

    def league_name(self):
        lg_name = self.lg.settings()
        return lg_name['name']

    def league_teams_id(self):
        self.cursor.execute(self.teams_by_league, ('428.l.' + self.cur_lg,))
        all_teams = self.cursor.fetchall()
        final_teams = ''
        for i in all_teams:
            final_teams += i[0] + '\n'
        return final_teams
        # all_ids = ""
        # for i in self.teames_in_league.keys():
        #     all_ids += self.teames_in_league[i]['team_key'] + "\n"
        # return all_ids

    # get the team roster you want
    # team key starts with 428.l.cur_lg.t. and then the number at the end of the url for each team. I'm 6, Yoavi 11.
    def get_team(self, team_key):

        self.cursor.execute(self.get_team_roster_by_team_key, (team_key,))
        team_roster = self.cursor.fetchall()
        return team_roster

    def get_teamkey(self, team_name):
        # team_info =  self.lg.get_team(team_name)
        team_info = self.lg.get_team(team_name)
        return team_info[team_name].team_key

    def get_matchup(self, week_num):
        team = self.lg.to_team(self.lg.team_key())
        return team.matchup(week_num)

    ### get user's team key
    def team_key(self):
        return self.lg.team_key()

    def is_injuerd(self, player):
        is_il = False
        try:
            pd = self.lg.player_details(player)
            is_il = False
            for i in pd[0]['eligible_positions']:
                if 'IL' in i['position']:
                    is_il = True
            return is_il
        except RuntimeError:
            return is_il
