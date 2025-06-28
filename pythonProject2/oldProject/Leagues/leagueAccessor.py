import pandas as pd
import pyodbc
from pythonProject2.oldProject.DataBase import DataBase as db
from pythonProject2.oldProject.DataBase import find_current_year
from Leagues.league import League
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from Teams.team import Team
from Players.player import Player
from Players.playerAccessor import *


class LeagueAccessor():
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()
    sc = OAuth2(None, None, from_file='oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
    last_season_fantasy_cat = "last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                              "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"

    ## get league stats for all teams
    current_league_stats = f"select team_name,{current_fantasy_cat} from dbo.yahoo_league_teams where league_name =?"
    last_season_league_stats = f"select team_name,{last_season_fantasy_cat} from dbo.yahoo_league_teams where league_name =?"


### insrert all the leagus I am in into table leagues
def sync_leagues_to_database():
    insert_query_game = "INSERT INTO leagues (league_id , league_name) VALUES ( ?, ?)"
    for league_id in LeagueAccessor.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            league_info = LeagueAccessor.yahoo_game.to_league(league_id).settings()
            league = League(league_info['league_key'], league_info['name'])
            data = (league.league_id, league.league_name)
            LeagueAccessor.cursor.execute(insert_query_game, data)

    # Commit the changes to the database
    LeagueAccessor.connection.commit()

    # Close the cursor and connection
    LeagueAccessor.cursor.close()
    LeagueAccessor.connection.close()


def league_stats(season_stats, league: League):
    if season_stats == find_current_year():
        apply_sql = LeagueAccessor.current_league_stats
        df = pd.read_sql_query(apply_sql, LeagueAccessor.connection, params=[league.league_name])

    else:
        apply_sql = LeagueAccessor.last_season_league_stats
        df = pd.read_sql_query(apply_sql, LeagueAccessor.connection, params=[league.league_name])
    df.set_index('team_name', inplace=True)
    return df


def get_free_agents(league: League, position):
    lg = db.yahoo_game.to_league(league.league_id)
    list_of_free_agents = []
    for i in lg.free_agents(position):
        list_of_free_agents.append(i['name'])
    return list_of_free_agents


def get_best_fa_in_categories(season_stats, league, position, list_of_cat):
    best_fa_list = {}
    free_agent_list = get_free_agents(league, position)

    for fa in free_agent_list:
        try:
            fa_player = Player(*get_player_object(fa))
            best_fa_list.update({fa_player.player_name:specific_categories_points(season_stats, fa_player, list_of_cat)})
        except IndexError:
            continue
    sorted_best_fa_dict = dict(sorted(best_fa_list.items(),key=lambda item: item[1],reverse=True))

    return sorted_best_fa_dict
