import sqlite3

from nba_api.stats.endpoints import playercareerstats, commonplayerinfo
from nba_api.stats.static import players, teams
import pyodbc
from Players.player import Player
import pandas as pd
from sqlalchemy import create_engine


class PlayerAccesor(object):
    MAX_PLAYERS = 10  # example
    get_all_active_players = "select id,full_name,first_name,last_name from dbo.nba_players"
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()

    data = "FGM,FGA,FG_PCT,FTM,FTA,FT_PCT,FG3M,PTS,REB,AST,STL,BLK,TOV"
    current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
    last_season_fantasy_cat = "last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                              "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    ## gets stats of current season by id
    current_stats_query = f"select {current_fantasy_cat} from dbo.nba_players where id=?"
    ## get stats of last season per id
    last_season_stats_query = f"select {last_season_fantasy_cat} from dbo.nba_players where id=?"
    ## get nba_team_name by player name
    get_nba_team_name = "select nba_team_name from dbo.nba_players where full_name=?"


def get_players_new_stats(nba_player):
    curr_player_stats = pg_adj_fantasy('2023-24', nba_player, True)
    #return curr_player_stats
    return (get_player_nba_team(nba_player), curr_player_stats['FGM'].iloc[0].round(3),
            curr_player_stats['FGA'].iloc[0].round(3),
            curr_player_stats['FG_PCT'].iloc[0].round(3), curr_player_stats['FTM'].iloc[0].round(3),
            curr_player_stats['FTA'].iloc[0].round(3), curr_player_stats['FT_PCT'].iloc[0].round(3),
            curr_player_stats['FG3M'].iloc[0].round(3), curr_player_stats['PTS'].iloc[0].round(3),
            curr_player_stats['REB'].iloc[0].round(3), curr_player_stats['AST'].iloc[0].round(3),
            curr_player_stats['STL'].iloc[0].round(3), curr_player_stats['BLK'].iloc[0].round(3),
            curr_player_stats['TOV'].iloc[0].round(3), nba_player.id)


def get_all_players(from_api=False):
    if from_api:
        player_data = players.get_players()
    else:
        PlayerAccesor.cursor.execute(PlayerAccesor.get_all_active_players)
        player_data = PlayerAccesor.cursor.fetchall()
    return player_data


## career stats, can only be from api
def career_stats(player: Player):
    stats_by_career = playercareerstats.PlayerCareerStats(player_id=player.id)
    return stats_by_career.get_data_frames()[0]


##current year stats, can be from api(career stats) or from db
def current_season_stats(player: Player):
    stats_by_current_season = career_stats(player)[
        career_stats(player)['SEASON_ID'] == '2023-24']
    return stats_by_current_season


##last year stats, can be from api(career stats) or from db
def last_season_stats(player: Player):
    stats_by_last_season = career_stats(player)[
        career_stats(player)['SEASON_ID'] == '2022-23']
    return stats_by_last_season


##only stats that belongs to the fantasy 9 categories
def adj_fantasy(season_stats, player: Player):
    if season_stats == '2023-24':
        selected_columns_from_current_season = current_season_stats(player)[
            ['SEASON_ID', 'TEAM_ABBREVIATION', 'GP', 'FGM', 'FGA', 'FG_PCT', 'FTM', 'FTA', 'FT_PCT', 'FG3M',
             'PTS',
             'REB', 'AST', 'STL', 'BLK',
             'TOV']].copy()
        if len(selected_columns_from_current_season) <= 1:
            # for rookies or players who played for 1 team
            return selected_columns_from_current_season
        else:
            # for players who played in more than 1 team
            total_selected = selected_columns_from_current_season[
                selected_columns_from_current_season['TEAM_ABBREVIATION'] == 'TOT']
            return total_selected

    else:
        selected_columns_from_last_season = last_season_stats(player)[
            ['SEASON_ID', 'TEAM_ABBREVIATION', 'GP', 'FGM', 'FGA', 'FG_PCT', 'FTM', 'FTA', 'FT_PCT', 'FG3M',
             'PTS',
             'REB', 'AST', 'STL', 'BLK',
             'TOV']].copy()
        if len(selected_columns_from_last_season) <= 1:
            # for rookies or players who played for 1 team
            return selected_columns_from_last_season
        else:
            # for players who played in more than 1 team
            total_selected = selected_columns_from_last_season[
                selected_columns_from_last_season['TEAM_ABBREVIATION'] == 'TOT']
            return total_selected


### The stats that in the database
## currently when take from db, its return list, not df with columns. fix it later
def pg_adj_fantasy(season_stats, player: Player, from_api=False):
    if from_api:
        pg_adj = adj_fantasy(season_stats, player)
        for col in pg_adj.columns:

            if col != 'SEASON_ID' and col != 'TEAM_ABBREVIATION' and col != 'GP' and col != 'FT_PCT' and col != 'FG_PCT':
                try:
                    pg_adj[col] = float(pg_adj[col]) / float(pg_adj['GP'])
                except TypeError:
                    continue
    else:
        columns_name = PlayerAccesor.data.split(',')

        if season_stats == '2023-24':
            pg_adj = pd.read_sql_query(PlayerAccesor.current_stats_query, PlayerAccesor.connection, params=(player.id,))

        else:
            pg_adj = pd.read_sql_query(PlayerAccesor.last_season_stats_query, PlayerAccesor.connection,
                                       params=(player.id,))
        pg_adj.columns = columns_name
    return pg_adj


## get the nba team of the player
def get_player_nba_team(player: Player, from_api=False):
    if from_api:
        nba_team_abb = current_season_stats(player)['TEAM_ABBREVIATION'].iloc[0]
        nba_team = teams.find_team_by_abbreviation(nba_team_abb)
        team_name = nba_team['nickname']
    else:

        PlayerAccesor.cursor.execute(PlayerAccesor.get_nba_team_name, (player.full_name,))
        team_name = PlayerAccesor.cursor.fetchall()[0][0]

    return team_name


### insert all the players in the nba into the table players
def sync_players_to_database():
    # Define your SQL INSERT statement

    insert_query_players = f"INSERT INTO nba_players (id, last_name, first_name, full_name,nba_team_name," \
                           f"{PlayerAccesor.fantasy_cat}) " \
                           f"VALUES (?,?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "

    # Get the list of players
    player_data = players.get_all_players(True)

    # Iterate over the player data and insert each player into the database
    for player in player_data:
        if player['is_active'] is True:
            nba_player = Player(player)
            try:
                curr_player_stats = pg_adj_fantasy('2023-24',nba_player,True)
                last_player_stats = pg_adj_fantasy('2022-23',nba_player,True)
                data = (
                    nba_player.id, nba_player.last_name, nba_player.first_name, nba_player.full_name,
                    get_player_nba_team(nba_player,from_api=True),
                    curr_player_stats['FGM'].iloc[0].round(3), curr_player_stats['FGA'].iloc[0].round(3),
                    curr_player_stats['FG_PCT'].iloc[0].round(3), curr_player_stats['FTM'].iloc[0].round(3),
                    curr_player_stats['FTA'].iloc[0].round(3), curr_player_stats['FT_PCT'].iloc[0].round(3),
                    curr_player_stats['FG3M'].iloc[0].round(3), curr_player_stats['PTS'].iloc[0].round(3),
                    curr_player_stats['REB'].iloc[0].round(3), curr_player_stats['AST'].iloc[0].round(3),
                    curr_player_stats['STL'].iloc[0].round(3), curr_player_stats['BLK'].iloc[0].round(3),
                    curr_player_stats['TOV'].iloc[0].round(3), last_player_stats['FGM'].iloc[0].round(3),
                    last_player_stats['FGA'].iloc[0].round(3), last_player_stats['FG_PCT'].iloc[0].round(3),
                    last_player_stats['FTM'].iloc[0].round(3), last_player_stats['FTA'].iloc[0].round(3),
                    last_player_stats['FT_PCT'].iloc[0].round(3), last_player_stats['FG3M'].iloc[0].round(3),
                    last_player_stats['PTS'].iloc[0].round(3), last_player_stats['REB'].iloc[0].round(3),
                    last_player_stats['AST'].iloc[0].round(3), last_player_stats['STL'].iloc[0].round(3),
                    last_player_stats['BLK'].iloc[0].round(3), last_player_stats['TOV'].iloc[0].round(3))
                PlayerAccesor.cursor.execute(insert_query_players, data)
                print(data)
            except IndexError:
                try:
                    data = (
                        player['id'], player['last_name'], player['first_name'], player['full_name'],
                        get_player_nba_team(nba_player),
                        curr_player_stats['FGM'].iloc[0].round(3), curr_player_stats['FGA'].iloc[0].round(3),
                        curr_player_stats['FG_PCT'].iloc[0].round(3), curr_player_stats['FTM'].iloc[0].round(3),
                        curr_player_stats['FTA'].iloc[0].round(3), curr_player_stats['FT_PCT'].iloc[0].round(3),
                        curr_player_stats['FG3M'].iloc[0].round(3), curr_player_stats['PTS'].iloc[0].round(3),
                        curr_player_stats['REB'].iloc[0].round(3), curr_player_stats['AST'].iloc[0].round(3),
                        curr_player_stats['STL'].iloc[0].round(3), curr_player_stats['BLK'].iloc[0].round(3),
                        curr_player_stats['TOV'].iloc[0].round(3)
                        , None, None, None, None,
                        None, None, None, None, None, None, None, None, None)
                    PlayerAccesor.cursor.execute(insert_query_players, data)
                    print(data)
                except IndexError:
                    try:
                        data = (
                            nba_player.id, nba_player.last_name, nba_player.first_name, nba_player.full_name,
                            None, None, None,
                            None, None, None, None, None, None, None, None, None, None, None,
                            last_player_stats['FGM'].iloc[0].round(3),
                            last_player_stats['FGA'].iloc[0].round(3), last_player_stats['FG_PCT'].iloc[0].round(3),
                            last_player_stats['FTM'].iloc[0].round(3), last_player_stats['FTA'].iloc[0].round(3),
                            last_player_stats['FT_PCT'].iloc[0].round(3), last_player_stats['FG3M'].iloc[0].round(3),
                            last_player_stats['PTS'].iloc[0].round(3), last_player_stats['REB'].iloc[0].round(3),
                            last_player_stats['AST'].iloc[0].round(3), last_player_stats['STL'].iloc[0].round(3),
                            last_player_stats['BLK'].iloc[0].round(3), last_player_stats['TOV'].iloc[0].round(3))
                        PlayerAccesor.cursor.execute(insert_query_players, data)
                        print(data)
                    except IndexError:
                        data = (
                            nba_player.id, nba_player.last_name, nba_player.first_name, nba_player.full_name,
                            None, None,
                            None,
                            None, None, None, None, None, None, None, None, None, None, None, None, None,
                            None, None, None, None, None, None, None, None, None, None, None)
                        PlayerAccesor.cursor.execute(insert_query_players, data)
                        print(data)

    # Commit the changes to the database
    PlayerAccesor.connection.commit()

    # Close the cursor and connection
    PlayerAccesor.cursor.close()
    PlayerAccesor.connection.close()


### updates the player current stats
def update_players_db():
    update_query_players = f"UPDATE nba_players SET nba_team_name=?,current_FGM=?,current_FGA=?,current_FG_PCT=?," \
                           f"current_FTM=?,current_FTA=?,current_FT_PCT=?,current_FG3M=?," \
                           "current_PTS=?,current_REB=?,current_AST=?,current_STL=?,current_BLK=?,current_TOV = ? " \
                           "WHERE id = ? "

    affected_rows = 0
    player_data = get_all_players(from_api=True)
    player_data = [player for player in player_data if player['is_active']]
    for player in player_data:
        try:
            nba_player = Player(player)
            data = get_players_new_stats(nba_player)
            affected_rows = PlayerAccesor.cursor.execute(update_query_players, data).rowcount

            print(player, data)
        except IndexError:
            pass
    # print how much rows were updated
    print(affected_rows)
    # Commit the changes to the database
    PlayerAccesor.connection.commit()

    # Close the cursor and connection
    PlayerAccesor.cursor.close()
    PlayerAccesor.connection.close()


### searches for player in all my leagues and return all his info and stats
def search_player_in_leagues_from_db(player: Player):
    ## search for player in each league in which team he is
    search_sql = f"Select player_id,player_name,team_name,league_name" \
                 f" From dbo.team_player  " \
                 f"where player_name=?"
    PlayerAccesor.cursor.execute(search_sql,(player.full_name,))
    teams_of_player = PlayerAccesor.cursor.fetchall()
    return teams_of_player
# def is_rookie(player: Player):
#     try:
#         player_info = commonplayerinfo.CommonPlayerInfo(player_id=player.id)
#         player_info = player_info.get_data_frames()[0]
#     except ValueError:
#         return True
#     # Extract the rookie year
#     rookie_year = player.draft_year
#
#     # Check if the player's rookie year is the same as the current season
#     return rookie_year == '2023'
