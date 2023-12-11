import pandas as pd
import pyodbc
from YahooLeague import YahooLeague


### function that check what happens to your team when you change one player in another

def matchup_analyzer(week_num, cur_league, season_stats='2023-24'):
    columns_name = Tools.current_fantasy_cat.split(',')
    league = YahooLeague(cur_league)
    my_team = league.team_key()
    my_count = 0
    my_total_games = 0
    Tools.cursor.execute(Tools.get_team_roster_by_team_key, (my_team,))
    my_roster = Tools.cursor.fetchall()
    my_team_df = pd.DataFrame(columns=columns_name)
    for my_name in my_roster:
        Tools.cursor.execute(Tools.get_nba_team_name, ((my_name[0]),))
        my_team_name = Tools.cursor.fetchall()
        if league.is_injuerd(my_name[0]) is False:
            my_count += 1
            Tools.cursor.execute(Tools.games_in_matchup, (week_num, my_team_name[0][0], my_team_name[0][0]))
            my_count_games_in_matchup = Tools.cursor.fetchall()
            my_total_games += my_count_games_in_matchup[0][0]
            Tools.cursor.execute(Tools.get_player_stats, (my_name[0],))
            pg_player_stats = Tools.cursor.fetchall()
            stat_mult_in_games = [my_count_games_in_matchup[0][0] * pg_player_stats[0][i] for i in range(0, 13) if
                                  i != 2 or i != 5]
            my_team_df.loc[len(my_team_df)] = stat_mult_in_games

    ## opponet week
    opp_count = 0
    opp_total_games = 0
    opp_team = league.get_matchup(week_num)
    Tools.cursor.execute(Tools.get_team_roster_by_team_key, (opp_team,))
    opp_roster = Tools.cursor.fetchall()
    opp_team_df = pd.DataFrame(columns=columns_name)
    for opp_name in opp_roster:
        Tools.cursor.execute(Tools.get_nba_team_name, ((opp_name[0]),))
        opp_team_name = Tools.cursor.fetchall()
        if league.is_injuerd(opp_name[0]) is False:
            opp_count += 1
            Tools.cursor.execute(Tools.games_in_matchup, (week_num, opp_team_name[0][0], opp_team_name[0][0]))
            opp_count_games_in_matchup = Tools.cursor.fetchall()
            opp_total_games += opp_count_games_in_matchup[0][0]
            Tools.cursor.execute(Tools.get_player_stats, (opp_name[0],))
            pg_player_stats_opp = Tools.cursor.fetchall()
            stat_mult_in_games_opp = [opp_count_games_in_matchup[0][0] * pg_player_stats_opp[0][i] for i in range(0, 13)
                                      if i != 2 or i != 5]
            opp_team_df.loc[len(opp_team_df)] = stat_mult_in_games_opp

    final_df = pd.DataFrame([my_team_df.sum(), opp_team_df.sum()], columns=Tools.current_fantasy_cat.split(','))
    Tools.cursor.execute(Tools.get_yahoo_team_name, (my_team,))
    my_yahoo_team = Tools.cursor.fetchall()
    Tools.cursor.execute(Tools.get_yahoo_team_name, (opp_team,))
    opp_yahoo_team = Tools.cursor.fetchall()
    final_df = final_df.rename(index={0: my_yahoo_team[0][0], 1: opp_yahoo_team[0][0]})
    final_df.at[my_yahoo_team[0][0], 'current_FT_PCT'] = final_df.at[
                                                             my_yahoo_team[0][0], 'current_FT_PCT'] / my_total_games
    final_df.at[my_yahoo_team[0][0], 'current_FG_PCT'] = final_df.at[
                                                             my_yahoo_team[0][0], 'current_FG_PCT'] / my_total_games
    final_df.at[opp_yahoo_team[0][0], 'current_FT_PCT'] = final_df.at[
                                                              opp_yahoo_team[0][0], 'current_FT_PCT'] / opp_total_games
    final_df.at[opp_yahoo_team[0][0], 'current_FG_PCT'] = final_df.at[
                                                              opp_yahoo_team[0][0], 'current_FG_PCT'] / opp_total_games
    return final_df


class Tools:
    connection = pyodbc.connect('Driver={SQL Server};'
                                'Server=PC-URI;'
                                'Database=NBA_API;'
                                'Trusted_Connection=yes;')
    cursor = connection.cursor()
    fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                  "current_PTS,current_REB,current_AST,current_STL," \
                  "current_BLK,current_TOV,last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                  "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"
    current_fantasy_cat = "current_FGM,current_FGA,current_FG_PCT,current_FTM,current_FTA,current_FT_PCT,current_FG3M," \
                          "current_PTS,current_REB,current_AST,current_STL,current_BLK,current_TOV"
    last_season_fantasy_cat = "last_FGM,last_FGA,last_FG_PCT,last_FTM,last_FTA,last_FT_PCT,last_FG3M," \
                              "last_PTS,last_REB,last_AST,last_STL,last_BLK,last_TOV"

    ## count players in roster
    count_players_in_roster = "select count(*) FROM dbo.team_players where team_name = ?"
    ## get team name and stats
    team_sql = f"Select team_name, {fantasy_cat} FROM dbo.yahoo_league_teams where team_name = ? "
    ## get team roster
    team_roster_sql = "select player_name FROM dbo.team_players where team_name = ?"
    ## get league name
    leagues_sql = "SELECT league_name FROM dbo.leagues"
    ## search for player in each league in which team he is
    search_sql = f"Select player_id,player_name,team_name,league_name,{fantasy_cat}" \
                 f" From dbo.yahoo_team_players Join dbo.players on dbo.team_players.player_id = dbo.players.id " \
                 f"where player_name=?"
    ## get team roster by team_key
    get_team_roster_by_team_key = "select player_name from dbo.team_players where team_key =?"
    ## get nba_team_name by player name
    get_nba_team_name = "select nba_team_name from dbo.players where full_name=?"
    ## count how much time player plays in a week
    games_in_matchup = "select distinct count(*) from dbo.schedule " \
                       "where dbo.schedule.week_number = ? and (dbo.schedule.home_team=? or  dbo.schedule.away_team=?)"
    ## get player stats
    get_player_stats = f"select {current_fantasy_cat} from dbo.players where full_name=?"
    ## get team name bt team key
    get_yahoo_team_name = "select team_name from dbo.yahoo_league_teams where team_key = ?"
    ## get league stats for all teams
    league_stats = "select * from dbo.yahoo_league_teams where league_id =?"
