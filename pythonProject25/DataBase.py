from nba_api.stats.static import players
import pyodbc

from Players.player import Player
from Players.playerAccessor import PlayerAccesor
from Players.playerAnalyzer import PlayerAnalyzer
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from TeamAnalyzer import TeamAnalyzer
from YahooLeague import YahooLeague
import requests
from datetime import datetime




### insert all the teams from al the leagues I am in, into the table yahoo_league_teams
def sync_teams_to_database(commit_count=0):
    # insert from scratch

    insert_query_league = f"INSERT INTO league_teams (league_id,team_key,team_name,{DataBase.fantasy_cat}) VALUES (?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"


    ## just to get to the 31 team
    count = 0
    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = DataBase.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:
                count += 1

                end_of_league_id = league_id.split(".l.")[1]
                team_id = cur_teams[team_key]['team_id']
                cur_team_stats = TeamAnalyzer(end_of_league_id, team_id).pg_player_stats('2023-24')
                last_team_stats = TeamAnalyzer(end_of_league_id, team_id).pg_player_stats('2022-23')

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
                DataBase.cursor.execute(insert_query_league, data)
                # DataBase.cursor.execute(update_query_teams, data)
                commit_count += 1

                if commit_count >= 10:
                    DataBase.connection.commit()
                    commit_count = 0
    if commit_count > 0:
        DataBase.connection.commit()

    DataBase.connection.commit()

    # Close the cursor and connection
    DataBase.cursor.close()
    DataBase.connection.close()


### insrert all the leagus I am in into table leagues
def sync_leagues_to_database():
    insert_query_game = "INSERT INTO leagues (league_key , league_name, num_teams) VALUES ( ?, ?, ?)"
    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            data = (league_id, DataBase.yahoo_game.to_league(league_id).settings()['name'],
                    DataBase.yahoo_game.to_league(league_id).settings()['num_teams'])
            DataBase.cursor.execute(insert_query_game, data)

    # Commit the changes to the database
    DataBase.connection.commit()

    # Close the cursor and connection
    DataBase.cursor.close()
    DataBase.connection.close()


### insert all the players in all the leagues I am in into team_player table
def sync_team_player_to_database(commit_count=0, player_count=0):
    insert_query_team_player = "INSERT INTO team_player (team_player_id, team_key, player_id,player_name, team_name," \
                               "league_name) " \
                               "VALUES ( ?, ?,?, ?,?,?) "
    player_data = players.get_players()
    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = DataBase.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()
            for team in cur_teams:
                lg = YahooLeague(league_id.split(".l.")[1])
                team_roster = lg.get_team(cur_teams[team]['team_id'])
                for player in team_roster:
                    player_count += 1
                    print(player['name'], lg.league_name())
                    data = (player_count,
                            cur_teams[team]['team_key'],
                            PlayerAnalyzer(player['name']).get_id(), player['name'], cur_teams[team]['name'],
                            lg.league_name())
                    print(data)
                    DataBase.cursor.execute(insert_query_team_player, data)
                    commit_count += 1
                    if commit_count >= 30:
                        DataBase.connection.commit()
                        commit_count = 0
                if commit_count > 0:
                    DataBase.connection.commit()
    DataBase.cursor.close()
    DataBase.connection.close()


def update_league_teams_db(commit_count=0):
    update_query_teams = f"UPDATE league_teams " \
                         f"SET current_FGM=?,current_FGA=?,current_FG_PCT=?,current_FTM=?,current_FTA=?,current_FT_PCT=?" \
                         f",current_FG3M=?,current_PTS=?,current_REB=?,current_AST=?,current_STL=?,current_BLK=?" \
                         f",current_TOV = ?,last_FGM=?,last_FGA=?,last_FG_PCT=?,last_FTM=?,last_FTA=?,last_FT_PCT=?," \
                         f"last_FG3M=?,last_PTS=?,last_REB=?,last_AST=?,last_STL=?,last_BLK=?,last_TOV = ? " \
                         f"WHERE league_id = ? AND team_key = ? "
    affected_rows = 0
    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = DataBase.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:
                end_of_league_id = league_id.split(".l.")[1]
                team_id = cur_teams[team_key]['team_id']
                cur_team_stats = TeamAnalyzer(end_of_league_id, team_id).pg_player_stats('2023-24')
                last_team_stats = TeamAnalyzer(end_of_league_id, team_id).pg_player_stats('2022-23')

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
                affected_rows = DataBase.cursor.execute(update_query_teams, data).rowcount
                commit_count += 1
                if commit_count >= 10:
                    DataBase.connection.commit()
                    commit_count = 0

    if commit_count > 0:
        DataBase.connection.commit()
    print(affected_rows)
    # Close the cursor and connection
    DataBase.cursor.close()
    DataBase.connection.close()


def update_team_player_db(commit_count=0, player_count=0):
    update_query_team_player = "Update team_player SET  team_key=?, player_id=?,player_name=?, team_name=?," \
                               "league_name=? WHERE team_player_id=? "
    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = DataBase.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()
            for team in cur_teams:
                lg = YahooLeague(league_id.split(".l.")[1])
                team_roster = lg.get_team(cur_teams[team]['team_id'])
                for player in team_roster:
                    player_count += 1
                    print(player['name'], lg.league_name())
                    data = (
                            cur_teams[team]['team_key'],
                            PlayerAnalyzer(player['name']).get_id(), player['name'], cur_teams[team]['name'],
                            lg.league_name(),player_count)
                    print(data)
                    #print(f"Executing SQL: {update_query_team_player} with data: {data}")
                    DataBase.cursor.execute(update_query_team_player, data)
                    commit_count += 1
                    if commit_count >= 30:
                        DataBase.connection.commit()
                        commit_count = 0
    if commit_count > 0:
        DataBase.connection.commit()
    DataBase.cursor.close()
    DataBase.connection.close()


def schedule_db(commit_count=0):
    json_schdule = requests.get('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')
    insert_schedule_query = "Insert into schedule (game_id,game_date,home_team,away_team,week_number) VALUES (?,?,?,?,?)"

    json_data = json_schdule.json()
    season_opener_date = datetime(2023, 10, 24)
    for date in json_data["leagueSchedule"]["gameDates"]:
        for game in date['games']:
            if game['weekNumber'] > 0:
                sql_data = (
                    game['gameId'], date['gameDate'][:-9], game['homeTeam']['teamName'], game['awayTeam']['teamName'],
                    game['weekNumber'])
                print(sql_data)
                DataBase.cursor.execute(insert_schedule_query, sql_data)
                commit_count += 1
                if commit_count > 100:
                    DataBase.connection.commit()
                    commit_count = 0
    if commit_count > 0:
        DataBase.connection.commit()
    DataBase.cursor.close()
    DataBase.connection.close()


class DataBase:
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()
    sc = OAuth2(None, None, from_file='oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                  "current_PTS,current_REB,current_AST,current_STL," \
                  "current_BLK,current_TOV,last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                  "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
