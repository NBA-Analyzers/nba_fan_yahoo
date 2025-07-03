from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import pyodbc
from pythonProject2.oldProject.DataBase import DataBase as db


class YahooLeague:

    # cur_lg is the league number but in string
    def __init__(self, cur_lg):
        # get game object
        self.cur_lg = cur_lg
        self.lg = db.yahoo_game.to_league(self.cur_lg)

    def teams_league(self):
        teams_by_league = "select team_key from dbo.yahoo_league_teams where league_id = ?"

        db.cursor.execute(teams_by_league, (self.cur_lg,))
        all_teams = db.cursor.fetchall()
        final_teams = ''
        for i in all_teams:
            final_teams += i[0] + '\n'
        return final_teams

    def __len__(self):
        return len(self.teams_league().split("\n"))

    def league_name(self):
        lg_name = self.lg.settings()
        return lg_name['name']

    def league_teams_id(self):
        teams_by_league = "select team_key from dbo.yahoo_league_teams where league_id = ?"

        db.cursor.execute(teams_by_league, (self.cur_lg,))
        all_teams = db.cursor.fetchall()
        final_teams = ''
        for i in all_teams:
            final_teams += i[0] + '\n'
        return final_teams

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

