import pandas as pd
from nba_api.stats.static import players
import pyodbc

from Players.player import Player
from Players.playerAccessor import pg_adj_fantasy
from Players.playerAnalyzer import PlayerAnalyzer
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from Teams.teamAnalyzer import TeamAnalyzer
from Teams.team import Team
from YahooLeague import YahooLeague
import requests
from datetime import datetime


class TeamAccessor(object):
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()
    sc = OAuth2(None, None, from_file='oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    data = {'FGM': 0, 'FGA': 0, 'FG_PCT': [0], 'FTM': 0, 'FTA': 0, 'FT_PCT': [0], 'FG3M': [0], 'PTS': [0],
            'REB': [0], 'AST': [0], 'STL': [0], 'BLK': [0],
            'TOV': [0]}
    fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                  "current_PTS,current_REB,current_AST,current_STL," \
                  "current_BLK,current_TOV,last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                  "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
    TEAM_LENGTH = 0
    ## get team name and stats
    team_stats_query = f"Select  {fantasy_cat} FROM dbo.league_teams where team_name = ? "


def pg_avg_stats_team(season_stats, team: Team):
    yl = YahooLeague(team.league_id)
    team_roster = yl.get_team(team.team_key)
    team_total_df = pd.DataFrame(TeamAccessor.data)
    df_fantasy_cat = pd.DataFrame(TeamAccessor.data)
    list_team_roster = [i[0] for i in team_roster]

    for player_info in players.get_players():
        if player_info['full_name'] in list_team_roster:
            player = Player(player_info)
            temp_df = pg_adj_fantasy(season_stats, player, True)
            if temp_df.empty or yl.is_injuerd(player_info['full_name']):
                continue
            TeamAccessor.TEAM_LENGTH += 1
            df_fantasy_cat = pg_adj_fantasy(season_stats, player, True)

        for column in team_total_df.columns:
            if column in df_fantasy_cat.columns:
                try:
                    team_total_df.at[TeamAccessor.TEAM_LENGTH - 1, column] = float(df_fantasy_cat[column])
                except TypeError:
                    continue

    total_team = team_total_df.sum()
    total_team['FG_PCT'] = total_team['FGM'] / total_team['FGA']
    total_team['FT_PCT'] = total_team['FTM'] / total_team['FTA']

    return pd.DataFrame(data=total_team).T


def pg_player_stats(season_stats, team: Team, from_api=False):
    if from_api:
        stats = pg_avg_stats_team(season_stats, team)
        pg_play_stats = pd.DataFrame(stats / TeamAccessor.TEAM_LENGTH)
        pg_play_stats['FG_PCT'] = pg_play_stats['FG_PCT'] * TeamAccessor.TEAM_LENGTH
        pg_play_stats['FT_PCT'] = pg_play_stats['FT_PCT'] * TeamAccessor.TEAM_LENGTH

    else:
        TeamAccessor.cursor.execute(TeamAccessor.team_stats_query, (team.team_name,))
        df_of_sql = TeamAccessor.cursor.fetchall()
        pg_play_stats = pd.DataFrame(TeamAccessor.data)
        col = 0
        for i in pg_play_stats.columns:
            pg_play_stats.loc[0, i] = df_of_sql[0][col]
            col += 1
    return pg_play_stats

    ### insert all the teams from al the leagues I am in, into the table yahoo_league_teams


def sync_teams_to_database(commit_count=0):
    # insert from scratch

    insert_query_league = f"INSERT INTO league_teams (league_id,team_key,team_name,{TeamAccessor.fantasy_cat}) VALUES (?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"

    ## just to get to the 31 team

    for league_id in TeamAccessor.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = TeamAccessor.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:


                team = Team(league_id, cur_teams[team_key])
                cur_team_stats = pg_player_stats('2023-24', team, True)
                last_team_stats = pg_player_stats('2022-23', team, True)

                data = (league_id, team_key, cur_teams[team_key]['name'], cur_team_stats['FGM'].iloc[0].round(3),
                        cur_team_stats['FGA'].iloc[0].round(3),
                        cur_team_stats['FG_PCT'].iloc[0].round(3), cur_team_stats['FTM'].iloc[0].round(3),
                        cur_team_stats['FTA'].iloc[0].round(3), cur_team_stats['FT_PCT'].iloc[0].round(3),
                        cur_team_stats['FG3M'].iloc[0].round(3), cur_team_stats['PTS'].iloc[0].round(3),
                        cur_team_stats['REB'].iloc[0].round(3), cur_team_stats['AST'].iloc[0].round(3),
                        cur_team_stats['STL'].iloc[0].round(3), cur_team_stats['BLK'].iloc[0].round(3),
                        cur_team_stats['TOV'].iloc[0].round(3), last_team_stats['FGM'].iloc[0].round(3),
                        last_team_stats['FGA'].iloc[0].round(3), last_team_stats['FG_PCT'].iloc[0].round(3),
                        last_team_stats['FTM'].iloc[0].round(3), last_team_stats['FTA'].iloc[0].round(3),
                        last_team_stats['FT_PCT'].iloc[0].round(3), last_team_stats['FG3M'].iloc[0].round(3),
                        last_team_stats['PTS'].iloc[0].round(3),
                        last_team_stats['REB'].iloc[0].round(3), last_team_stats['AST'].iloc[0].round(3),
                        last_team_stats['STL'].iloc[0].round(3),
                        last_team_stats['BLK'].iloc[0].round(3), last_team_stats['TOV'].iloc[0].round(3))
                print(cur_teams[team_key]['name'])
                TeamAccessor.cursor.execute(insert_query_league, data)

                commit_count += 1

                if commit_count >= 10:
                    TeamAccessor.connection.commit()
                    commit_count = 0
    if commit_count > 0:
        TeamAccessor.connection.commit()

    TeamAccessor.connection.commit()

    # Close the cursor and connection
    TeamAccessor.cursor.close()
    TeamAccessor.connection.close()


def update_league_teams_db(commit_count=0):
    update_query_teams = f"UPDATE league_teams " \
                         f"SET current_FGM=?,current_FGA=?,current_FG_PCT=?,current_FTM=?,current_FTA=?,current_FT_PCT=?" \
                         f",current_FG3M=?,current_PTS=?,current_REB=?,current_AST=?,current_STL=?,current_BLK=?" \
                         f",current_TOV = ?,last_FGM=?,last_FGA=?,last_FG_PCT=?,last_FTM=?,last_FTA=?,last_FT_PCT=?," \
                         f"last_FG3M=?,last_PTS=?,last_REB=?,last_AST=?,last_STL=?,last_BLK=?,last_TOV = ? " \
                         f"WHERE league_id = ? AND team_key = ? "
    affected_rows = 0
    for league_id in TeamAccessor.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = TeamAccessor.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:
                team = Team(league_id, cur_teams[team_key])
                cur_team_stats = pg_player_stats('2023-24', team, True)
                last_team_stats = pg_player_stats('2022-23', team, True)

                data = (
                    cur_team_stats['FGM'].iloc[0].round(3), cur_team_stats['FGA'].iloc[0].round(3),
                    cur_team_stats['FG_PCT'].iloc[0].round(3), cur_team_stats['FTM'].iloc[0].round(3),
                    cur_team_stats['FTA'].iloc[0].round(3), cur_team_stats['FT_PCT'].iloc[0].round(3),
                    cur_team_stats['FG3M'].iloc[0].round(3), cur_team_stats['PTS'].iloc[0].round(3),
                    cur_team_stats['REB'].iloc[0].round(3), cur_team_stats['AST'].iloc[0].round(3),
                    cur_team_stats['STL'].iloc[0].round(3), cur_team_stats['BLK'].iloc[0].round(3),
                    cur_team_stats['TOV'].iloc[0].round(3), last_team_stats['FGM'].iloc[0].round(3),
                    last_team_stats['FGA'].iloc[0].round(3), last_team_stats['FG_PCT'].iloc[0].round(3),
                    last_team_stats['FTM'].iloc[0].round(3), last_team_stats['FTA'].iloc[0].round(3),
                    last_team_stats['FT_PCT'].iloc[0].round(3), last_team_stats['FG3M'].iloc[0].round(3),
                    last_team_stats['PTS'].iloc[0].round(3),
                    last_team_stats['REB'].iloc[0].round(3), last_team_stats['AST'].iloc[0].round(3),
                    last_team_stats['STL'].iloc[0].round(3),
                    last_team_stats['BLK'].iloc[0].round(3), last_team_stats['TOV'].iloc[0].round(3), league_id,
                    team_key
                )
                print(cur_teams[team_key]['name'])
                affected_rows = TeamAccessor.cursor.execute(update_query_teams, data).rowcount
                commit_count += 1
                if commit_count >= 10:
                    TeamAccessor.connection.commit()
                    commit_count = 0

    if commit_count > 0:
        TeamAccessor.connection.commit()
    print(affected_rows)
    # Close the cursor and connection
    TeamAccessor.cursor.close()
    TeamAccessor.connection.close()

