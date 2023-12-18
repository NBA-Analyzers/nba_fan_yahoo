from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import pyodbc


class YahooLeague:

    # cur_lg is the league number but in string
    def __init__(self, cur_lg):
        # connect to yahoo api

        self.sc = OAuth2(None, None, from_file='oauth22.json')
        # get game object
        self.gm = yfa.Game(self.sc, 'nba')
        self.cur_lg = cur_lg
        self.lg = self.gm.to_league('428.l.' + self.cur_lg)
        self.teames_in_league = self.lg.teams()

    def teams_league(self):

        all_teams = ""
        for i in self.teames_in_league.keys():
            all_teams += self.teames_in_league[i]['name'] + "\n"
        return all_teams

    def __len__(self):
        return len(self.teams_league().split("\n"))

    def league_name(self):
        lg_name = self.lg.settings()
        return lg_name['name']

    def league_teams_id(self):
        all_ids = ""
        for i in self.teames_in_league.keys():
            all_ids += self.teames_in_league[i]['team_key'] + "\n"
        return all_ids

    # get the team roster you want
    # team key starts with 428.l.cur_lg.t. and then the number at the end of the url for each team. I'm 6, Yoavi 11.
    def get_team(self, team_key):
        team = self.lg.to_team('428.l.' + self.cur_lg + '.t.' + team_key)
        return team.roster()

    def get_teamkey(self, team_name):
        # team_info =  self.lg.get_team(team_name)
        team_info = self.lg.get_team(team_name)
        return team_info[team_name].team_key

    def sync_game_to_database(self):
        connection = pyodbc.connect('Driver={SQL Server};'
                                    'Server=PC-URI;'
                                    'Database=NBA_API;'
                                    'Trusted_Connection=yes;')

        cursor = connection.cursor()
        insert_query_game = "INSERT INTO leagues (league_key , league_name, num_teams) VALUES ( ?, ?, ?)"

        for league_id in self.gm.league_ids():
            if league_id[0:3] == "428":
                # print(type(self.gm.to_league(league_id).settings()['url']))

                data = (league_id, self.gm.to_league(league_id).settings()['name'],
                        self.gm.to_league(league_id).settings()['num_teams'])
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
        insert_query_league = "INSERT INTO teams_league (league_key , team_key,team_name, num_of_players) VALUES ( ?, ?, ?,?)"
        for league_id in self.gm.league_ids():
            if league_id[0:3] == "428":
                cur_league = self.gm.to_league(league_id)
                cur_teams = cur_league.teams()
                for team_id in cur_teams:

                    data = (league_id,cur_teams[team_id]['team_key'],cur_teams[team_id]['name'],
                            len(cur_teams[team_id]))
                    cursor.execute(insert_query_league, data)
                    # Commit the changes to the database
        connection.commit()

        # Close the cursor and connection
        cursor.close()
        connection.close()
#
# #     data = (player['id'], player['last_name'], player['first_name'], player['full_name'], player['is_active'])
#     cursor.execute(insert_query_players, data)
#
# # Commit the changes to the database
# connection.commit()
#
# # Close the cursor and connection
# cursor.close()
# connection.close()
