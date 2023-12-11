from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import players, teams
import pyodbc
from Players.player import Player
import pandas as pd
from DataBase import DataBase as db, find_current_year, find_last_year


class PlayerAccesor(object):
    GET_ALL_ACTIVE_PLAYERS = "select player_id,player_name from dbo.players"
    ## gets stats of current season by id
    CURRENT_STATS_QUERY = f"select {db.CURRENT_FANTASY_CAT} from dbo.players where player_id=?"
    ## get stats of last season per id
    LAST_SEASON_STATS_QUERY = f"select {db.LAST_SEASON_FANTASY_CAT} from dbo.players where player_id=?"
    ## get nba_team_name by player name
    GET_NBA_TEAM_NAME = "select nba_team_name from dbo.players where player_name=?"
    THIRTEEN_NONE = [None] * 13
    insert_query_players = f"INSERT INTO players (player_id, player_name,nba_team_name," \
                           f"{db.CURRENT_FANTASY_CAT},{db.LAST_SEASON_FANTASY_CAT}) " \
                           f"VALUES (?,?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
    get_player_object_query = "select player_name,player_id from dbo.players where player_name = ?"
def get_player_object(player_name):
    db.cursor.execute(PlayerAccesor.get_player_object_query, (player_name,))
    player_object = db.cursor.fetchall()
    return player_object[0]
## career stats, can only be from api
def career_stats(player: Player):
    stats_by_career = playercareerstats.PlayerCareerStats(player_id=player.player_id)
    return stats_by_career.get_data_frames()[0]


##current year stats, can be from api(career stats) or from db
def current_season_stats(player: Player):
    stats_by_current_season = career_stats(player)[
        career_stats(player)['SEASON_ID'] == find_current_year()]
    return stats_by_current_season


##last year stats, can be from api(career stats) or from db
def last_season_stats(player: Player):
    stats_by_last_season = career_stats(player)[career_stats(player)['SEASON_ID'] == find_last_year()]
    return stats_by_last_season


##only stats that belongs to the fantasy 9 categories
def adj_fantasy(season_stats, player: Player):
    if season_stats == find_current_year():
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
        columns_name = db.ALL_FANTASY_CAT.split(',')

        if season_stats == find_current_year():
            pg_adj = pd.read_sql_query(db.CURRENT_STATS_QUERY, PlayerAccesor.connection, params=(player.id,))

        else:
            pg_adj = pd.read_sql_query(db.LAST_SEASON_STATS_QUERY, PlayerAccesor.connection,
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

        db.cursor.execute(PlayerAccesor.GET_NBA_TEAM_NAME, (player.player_name,))
        team_name = db.cursor.fetchall()[0][0]

    return team_name


def get_all_players(from_api=False):
    if from_api:
        player_data = players.get_players()
    else:
        db.cursor.execute(PlayerAccesor.GET_ALL_ACTIVE_PLAYERS)
        player_data = db.cursor.fetchall()
    return player_data


def get_players_new_stats(nba_player, season_stats):
    curr_player_stats = pg_adj_fantasy(season_stats, nba_player, True)
    try:
        all_current_stats = [curr_player_stats[stat].iloc[0].round(3) for stat in db.FANTASY_CAT_STATS.split(',')]
    except IndexError:
        return None
    # return curr_player_stats
    return all_current_stats


def get_player_id(player_name):
    player_data = players.get_active_players()

    # Iterate over the player data and insert each player into the database
    for player in player_data:
        if player['full_name'] == player_name:
            return player['id']


### insert all the players in the nba into the table players
def sync_players_to_database():
    # Define your SQL INSERT statement

    # Get the list of players

    player_data = players.get_active_players()

    # Iterate over the player data and insert each player into the database
    for player in player_data:
        nba_player = Player(player['full_name'], player['id'])
        all_current_stats = get_players_new_stats(nba_player, find_current_year())
        all_last_stats = get_players_new_stats(nba_player, find_last_year())

        if all_current_stats is not None and all_last_stats is not None:
            data = (nba_player.player_id, nba_player.player_name,
                    get_player_nba_team(nba_player, from_api=True),
                    *all_current_stats, *all_last_stats)
            db.cursor.execute(PlayerAccesor.insert_query_players, data)
            print(data)

        elif all_last_stats is not None and all_last_stats is None:
            ### players didn't play last year
            data = (
                nba_player.player_id, nba_player.player_name,
                get_player_nba_team(nba_player),
                *all_current_stats, *PlayerAccesor.THIRTEEN_NONE)
            db.cursor.execute(PlayerAccesor.insert_query_players, data)
            print(data)
        elif all_last_stats is None and all_last_stats is not None:
            ### players that didn't play this year until now
            data = (
                nba_player.player_id, nba_player.player_name,
                *PlayerAccesor.THIRTEEN_NONE, *all_last_stats)
            db.cursor.execute(PlayerAccesor.insert_query_players, data)
            print(data)
        else:
            data = (
                nba_player.player_id, nba_player.player_name,
                *PlayerAccesor.THIRTEEN_NONE, *PlayerAccesor.THIRTEEN_NONE)
            db.cursor.execute(PlayerAccesor.insert_query_players, data)
            print(data)

    # Commit the changes to the database
    db.connection.commit()

    # Close the cursor and connection
    db.cursor.close()
    db.connection.close()


### updates the player current stats
def update_players_db():
    columns_list = db.CURRENT_FANTASY_CAT.split(',')
    set_clause = ', '.join([f"{column} = ?" for column in columns_list])
    update_query_players = f"UPDATE players SET nba_team_name=?,{set_clause} WHERE player_id = ? "

    affected_rows = 0
    player_data = players.get_active_players()
    for player in player_data:
        try:
            nba_player = Player(player['full_name'], player['id'])
            data = (get_player_nba_team(nba_player, True), *get_players_new_stats(nba_player, find_current_year()),
                    nba_player.player_id)
            affected_rows = db.cursor.execute(update_query_players, data).rowcount

            print(player, data)
        except IndexError:
            pass
    # print how much rows were updated
    print(affected_rows)
    # Commit the changes to the database
    db.connection.commit()

    # Close the cursor and connection
    db.cursor.close()
    db.connection.close()


### searches for player in all my leagues and return all his info and stats
def search_player_in_leagues_from_db(player: Player):
    ## search for player in each league in which team he is
    search_sql = f"Select player_id,player_name,team_name,league_name" \
                 f" From dbo.team_player  " \
                 f"where player_name=?"
    db.cursor.execute(search_sql, (player.player_name,))
    teams_of_player = db.cursor.fetchall()
    return teams_of_player


def get_list_of_players_stats(players):
    query_template = f"SELECT {db.CURRENT_FANTASY_CAT} FROM dbo.players WHERE player_name IN ({', '.join('?' for _ in players)}) "
    db.cursor.execute(query_template, *players)
    PLAYERS_STATS_NEW_QUERY = db.cursor.fetchall()
    return PLAYERS_STATS_NEW_QUERY
