import json
from datetime import datetime

import numpy
import pandas as pd
import pyodbc

from YahooLeague import YahooLeague


class AdvancedTools:

    def __init__(self, cur_league='41083'):
        self.league = YahooLeague(cur_league)
        self.df = pd.DataFrame(self.league.lg.matchups())
        self.data = {'NAME': [], 'FGM/A': [], 'current_FG_PCT': [], 'FTM/A': [], 'current_FT_PCT': [],
                     'current_FG3M': [], 'current_PTS': [], 'current_REB': [],
                     'current_AST': [], 'current_STL': [], 'current_BLK': [], 'current_TOV': []}
        connection = pyodbc.connect('Driver={SQL Server};'
                                    'Server=PC-URI;'
                                    'Database=NBA_API;'
                                    'Trusted_Connection=yes;')
        self.cursor = connection.cursor()
        self.current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT," \
                                   "current_FG3M,current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
        ## search all games within the same week after the date
        self.later_date = "SELECT count(*) FROM dbo.schedule WHERE week_number = ? AND " \
                          "CONVERT(DATE, game_date, 101) >= CONVERT(DATE,?, 101) " \
                          "and (dbo.schedule.home_team=? or  dbo.schedule.away_team=?)"
        ## get team roster
        self.team_roster_sql = "select player_name FROM dbo.team_player where team_name = ?"
        ## get nba_team_name by player name
        self.get_nba_team_name = "select nba_team_name from dbo.nba_players where full_name=?"
        ## get player stats
        self.get_player_stats = f"select {self.current_fantasy_cat} from dbo.nba_players where full_name=?"

    #
    # def process_json(self,data):
    #     if isinstance(data, dict):
    #         # If the data is a dictionary, iterate over its key-value pairs
    #         for key, value in data.items():
    #             print(f"Key: {key}")
    #             process_json(value)  # Recursive call to handle nested structures
    #
    #     elif isinstance(data, list):
    #         # If the data is a list, iterate over its elements
    #         for item in data:
    #             process_json(item)  # Recursive call to handle elements in the list
    #
    #     else:
    #         # If the data is neither a dictionary nor a list, it's a leaf node
    #         print(f"Value: {data}")
    #
    def analyze_matchup(self, cur_league='41083'):

        bn = pd.DataFrame(self.df.fantasy_content.values.tolist()[1])['scoreboard']

        matchup_df = pd.DataFrame(self.data)
        count_row = 0
        count_col = 0
        try:
            for i in bn[1]['0']['matchups'].values():

                for j in (i['matchup']['0']['teams']).values():
                    try:
                        matchup_df.loc[count_row] = [None] * len(matchup_df.columns)

                        team_name = j['team'][0][2]['name']
                        matchup_df.iat[count_row, count_col] = team_name
                        for k in (j['team'][1]['team_stats']['stats']):
                            count_col += 1
                            matchup_df.iat[count_row, count_col] = k['stat']['value']

                        count_row += 1
                        count_col = 0
                    except TypeError:

                        continue

        except TypeError:
            pass
        # Call the recursive function with the JSON data
        return matchup_df

    def get_matchup_of_team(self, cur_team='DraCaris LeVert'):
        cur_df = self.analyze_matchup()
        row_of_team = cur_df.loc[cur_df['NAME'] == cur_team].index.to_numpy()[0]
        if row_of_team % 2 == 0:
            matchup_name = cur_df.loc[row_of_team + 1, 'NAME']
        else:

            matchup_name = (cur_df.loc[row_of_team - 1, 'NAME'])
        return matchup_name

    def projected_matchup(self, cur_team='DraCaris LeVert'):
        opp_team = self.get_matchup_of_team(cur_team)
        league_set = (self.df.fantasy_content.values.tolist()[1][0])
        week_number = league_set['current_week']
        current_date = league_set['edit_key']
        converted_date = datetime.strptime(current_date, '%Y-%m-%d').strftime('%m/%d/%Y')

        columns_name = self.current_fantasy_cat.split(',')
        games_count = 0
        cur_team_df = pd.DataFrame(columns=columns_name)
        final_df = pd.DataFrame()
        total_games_in_matchup = 0
        for m in range(2):
            if m == 0:
                self.cursor.execute(self.team_roster_sql, (cur_team,))
                cur_team_roster = self.cursor.fetchall()
            else:

                cur_team_df = pd.DataFrame(columns=columns_name)
                self.cursor.execute(self.team_roster_sql, (opp_team,))
                cur_team_roster = self.cursor.fetchall()
            for full_name in cur_team_roster:
                if self.league.is_injuerd(full_name[0]) is False:
                    self.cursor.execute(self.get_nba_team_name, (full_name[0],))
                    nba_team = self.cursor.fetchall()
                    try:
                        self.cursor.execute(self.later_date,
                                            (week_number, converted_date, nba_team[0][0], nba_team[0][0],))
                        games_in_schedule = self.cursor.fetchall()
                        total_games_in_matchup += games_in_schedule[0][0]
                    except IndexError:
                        continue
                    self.cursor.execute(self.get_player_stats, (full_name[0],))
                    pg_player_stats_opp = self.cursor.fetchall()
                    total_stat_player = [games_in_schedule[0][0] * pg_player_stats_opp[0][j] for j in range(0, 13)]

                    cur_team_df.loc[len(cur_team_df)] = total_stat_player
            row_sum = cur_team_df.sum()
            row_sum.at['current_FG_PCT'] = row_sum.at['current_FG_PCT'] / total_games_in_matchup
            row_sum.at['current_FT_PCT'] = row_sum.at['current_FT_PCT'] / total_games_in_matchup
            final_df = pd.concat([final_df, row_sum.to_frame().transpose()], ignore_index=True)
            # final_df = final_df.rename(index={0: my_yahoo_team[0][0], 1: opp_yahoo_team[0][0]})
            total_games_in_matchup = 0
        return final_df.rename(index={0: cur_team, 1: opp_team})

    def combine_match(self, cur_team='yoav\'s Champion Team'):
        past_matchup = self.analyze_matchup(cur_team)
        projected_matchup = self.projected_matchup(cur_team)
        opp_team = self.get_matchup_of_team(cur_team)
        my_team_past_matchup = past_matchup[past_matchup['NAME'] == cur_team]
        opp_team_past_matchup = past_matchup[past_matchup['NAME'] == opp_team]

        for col in projected_matchup:
            if col in my_team_past_matchup:
                try:
                    projected_matchup.loc[cur_team, col] = float(projected_matchup.loc[cur_team, col]) + \
                                                           float(opp_team_past_matchup[col].iloc[0])
                    projected_matchup.loc[opp_team, col] = float(projected_matchup.loc[opp_team, col]) + \
                                                           float(opp_team_past_matchup[col].iloc[0])
                except KeyError:
                    continue
        try:
            projected_matchup.loc[cur_team, 'current_FGM'] = projected_matchup.loc[cur_team, 'current_FGM'] + float(
                my_team_past_matchup['FGM/A'].iloc[0].split('/')[0])
            projected_matchup.loc[cur_team, 'current_FGA'] = projected_matchup.loc[cur_team, 'current_FGA'] + float(
                my_team_past_matchup['FGM/A'].iloc[0].split('/')[1])
            projected_matchup.loc[opp_team, 'current_FGM'] = projected_matchup.loc[opp_team, 'current_FGM'] + float(
                opp_team_past_matchup['FGM/A'].iloc[0].split('/')[0])
            projected_matchup.loc[opp_team, 'current_FGA'] = projected_matchup.loc[opp_team, 'current_FGA'] + float(
                opp_team_past_matchup['FGM/A'].iloc[0].split('/')[1])

        except KeyError:
            pass
        try:
            projected_matchup.loc[cur_team, 'current_FTM'] = projected_matchup.loc[cur_team, 'current_FTM'] + float(
                my_team_past_matchup['FTM/A'].iloc[0].split('/')[0])
            projected_matchup.loc[cur_team, 'current_FTA'] = projected_matchup.loc[cur_team, 'current_FTA'] + float(
                my_team_past_matchup['FTM/A'].iloc[0].split('/')[1])
            projected_matchup.loc[cur_team, 'current_FTM'] = projected_matchup.loc[cur_team, 'current_FTM'] + float(
                my_team_past_matchup['FTM/A'].iloc[0].split('/')[0])
            projected_matchup.loc[opp_team, 'current_FTA'] = projected_matchup.loc[opp_team, 'current_FTA'] + float(
                opp_team_past_matchup['FTM/A'].iloc[0].split('/')[1])
        except KeyError:
            pass
        projected_matchup.loc[cur_team, 'current_FG_PCT'] = projected_matchup.loc[cur_team, 'current_FGM'] / \
                                                            projected_matchup.loc[cur_team, 'current_FGA']
        projected_matchup.loc[cur_team, 'current_FT_PCT'] = projected_matchup.loc[cur_team, 'current_FTM'] / \
                                                            projected_matchup.loc[cur_team, 'current_FTA']

        return projected_matchup
