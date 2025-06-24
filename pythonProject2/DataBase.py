import pyodbc

import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2

import requests
from datetime import datetime


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


def find_current_year():
    if datetime.now().month < 7:
        current_year = datetime.now().year
        last_year = current_year - 1
        formatted_years = f"{str(last_year)}-{str(current_year)[2:]}"
    else:
        current_year = datetime.now().year
        next_year = current_year + 1
        formatted_years = f"{current_year}-{str(next_year)[2:]}"
    return formatted_years


def find_last_year():
    if datetime.now().month < 7:
        current_year = datetime.now().year
        last_year = current_year - 1
        formatted_years = f"{str(last_year - 1)}-{str(last_year)[2:]}"
    else:
        current_year = datetime.now().year
        last_year = current_year - 1
        formatted_years = f"{last_year}-{str(current_year)[2:]}"
    return formatted_years


class DataBase:

    sc = OAuth2(None, None, from_file='./pythonProject2/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')

    ALL_FANTASY_CAT = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                      "current_PTS,current_REB,current_AST,current_STL," \
                      "current_BLK,current_TOV,last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                      "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    CURRENT_FANTASY_CAT = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
    FANTASY_CAT_STATS = "FGM,FGA,FG_PCT,FTM,FTA,FT_PCT,FG3M,PTS,REB,AST,STL,BLK,TOV"
    LAST_SEASON_FANTASY_CAT = "last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                              "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    STATS_FOR_MATCHUP = 'NAME,FGM/A,current_FG_PCT,FTM/A,current_FT_PCT,current_FG3M,current_PTS,current_REB,' \
                        'current_AST,current_STL,current_BLK,current_TOV'

    def connect_to_db():
        connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
        cursor = connection.cursor()