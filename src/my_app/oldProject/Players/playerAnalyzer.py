from Players.playerAccessor import *


## for only single player
class PlayerAnalyzer:
    players_rename = {"Xavier Tillman Sr.": "Xavier Tillman", "P.J. Washington Jr.": "P.J. Washington"}
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()
    fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                  "current_PTS,current_REB,current_AST,current_STL," \
                  "current_BLK,current_TOV,last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                  "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    ## get league name
    leagues_sql = "SELECT league_name FROM dbo.leagues"
    ## search for player in each league in which team he is
    search_sql = f"Select player_id,player_name,team_name,league_name,{fantasy_cat}" \
                 f" From dbo.team_player Join dbo.nba_players on dbo.team_player.player_id = dbo.nba_players.id " \
                 f"where player_name=?"


def _rename_players(full_name):
    if full_name in PlayerAnalyzer.players_rename:
        full_name = PlayerAnalyzer.players_rename[full_name]

    return full_name


### function that check where a player you search for is playing and if he is free agent
def search_player_in_leagues(player: Player):
    PlayerAnalyzer.cursor.execute(PlayerAnalyzer.leagues_sql)
    leagues = PlayerAnalyzer.cursor.fetchall()
    list_of_leagues = []
    search_player_query = search_player_in_leagues_from_db(player)
    for j in search_player_query:
        list_of_leagues.append(j[3])
        if j is not None:
            print(f"{player.player_name} is in {j[2]} team in {j[3]} league")
    for i in leagues:
        if i[0] not in list_of_leagues:
            print(f"{player.player_name} is FA in {i[0]} league")


def get_best_player_overall_in_categories(seasom_stats, position, list_of_cat):
    best_player_list = {}
    for i in get_all_players():
        player =Player(*i)
        best_player_list.update({player.player_name:specific_categories_points(seasom_stats,player,list_of_cat)})
    sorted_best_player= dict(sorted(best_player_list.items(),key=lambda item: item[1],reverse=True))

    return sorted_best_player