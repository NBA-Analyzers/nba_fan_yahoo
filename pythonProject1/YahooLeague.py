from sys import prefix
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import pyodbc



class YahooLeague:
    NBA_SPORT_CODE = '428'
    # connect to yahoo api
    yahoo_oauth_cred = OAuth2(None, None, from_file='oauth22.json')
    yahoo_game_service = yfa.Game(yahoo_oauth_cred, 'nba')

    # cur_lg is the league number but in string
    def __init__(self, cur_lg):
        self.league_yahoo = self.yahoo_game_service.to_league(f"{self.NBA_SPORT_CODE}.l.{cur_lg}")
        self.teames_in_league = self.league_yahoo.teams()

    def teams_league(self):
        all_teams = ""
        for i in self.teames_in_league.keys():
            all_teams += self.teames_in_league[i]['name'] + "\n"
        return all_teams

    def __len__(self):
        return len(self.teams_league().split("\n"))

    def league_name(self):
        return self.league_yahoo.settings()['name']

    def league_teams_id(self):
        all_ids = ""
        for i in self.teames_in_league.keys():
            all_ids += self.teames_in_league[i]['team_key'] + "\n"
        return all_ids

    # get the team roster you want
    def get_team_roster(self, team_key):
        team = self.league_yahoo.to_team(team_key)
        return team.roster()

    def get_team_key_by_name(self, team_name):
        # team_info =  self.lg.get_team(team_name)
        team_info = self.league_yahoo.get_team(team_name)
        return team_info[team_name].team_key

    def sync_game_to_database(self):
        connection = pyodbc.connect('Driver={SQL Server};'
                                    'Server=PC-URI;'
                                    'Database=NBA_API;'
                                    'Trusted_Connection=yes;')

        cursor = connection.cursor()
        insert_query_game = "INSERT INTO leagues (league_key , league_name, num_teams) VALUES ( ?, ?, ?)"

        for league_id in self.yahoo_game_service.league_ids():
            if league_id[0:3] == self.NBA_SPORT_CODE:
                data = (
                    league_id, 
                    self.yahoo_game_service.to_league(league_id).settings()['name'],
                    self.yahoo_game_service.to_league(league_id).settings()['num_teams']
                    )
                cursor.execute(insert_query_game, data)
        # Commit the changes to the database
        connection.commit()

        # Close the cursor and connection
        cursor.close()
        connection.close()

    def sync_league_to_database(self):
        connection = pyodbc.connect('Driver={SQL Server};'
                                    'Server=PC-URI;'
                                    'Database=NBA_API;'
                                    'Trusted_Connection=yes;')

        cursor = connection.cursor()
        insert_query_league = "INSERT INTO teams_league (league_key , team_key, team_name, num_of_players) VALUES ( ?, ?, ?,?)"
        for league_id in self.yahoo_game_service.league_ids():
            if league_id[0:3] == self.NBA_SPORT_CODE:
                cur_league = self.yahoo_game_service.to_league(league_id)
                cur_teams = cur_league.teams()
                for team_id in cur_teams:

                    data = (
                        league_id,
                        cur_teams[team_id]['team_key'],
                        cur_teams[team_id]['name'],
                        len(cur_teams[team_id])
                        )
                    cursor.execute(insert_query_league, data)
                    # Commit the changes to the database
        connection.commit()

        # Close the cursor and connection
        cursor.close()
        connection.close()

