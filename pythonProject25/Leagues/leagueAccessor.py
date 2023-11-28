import pandas as pd
import pyodbc
from Leagues.league import League
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from Teams.team import Team


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
    current_league_stats = f"select team_name,{current_fantasy_cat} from dbo.league_teams where league_id =?"
    last_season_league_stats = f"select team_name,{last_season_fantasy_cat} from dbo.league_teams where league_id =?"


### insrert all the leagus I am in into table leagues
def sync_leagues_to_database():
    insert_query_game = "INSERT INTO leagues (league_key , league_name, num_teams) VALUES ( ?, ?, ?)"
    for league_id in LeagueAccessor.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            league = League(LeagueAccessor.yahoo_game.to_league(league_id).settings())
            data = (league.league_key, league.league_name,
                    league.num_teams)
            LeagueAccessor.cursor.execute(insert_query_game, data)

    # Commit the changes to the database
    LeagueAccessor.connection.commit()

    # Close the cursor and connection
    LeagueAccessor.cursor.close()
    LeagueAccessor.connection.close()


def league_stats(season_stats, league: League):
    if season_stats=='2023-24':
        apply_sql = LeagueAccessor.current_league_stats
        df = pd.read_sql_query(apply_sql, LeagueAccessor.connection, params=[league.league_key])

    else:
        apply_sql = LeagueAccessor.last_season_league_stats
        df = pd.read_sql_query(apply_sql, LeagueAccessor.connection, params=[league.league_key])
    return df