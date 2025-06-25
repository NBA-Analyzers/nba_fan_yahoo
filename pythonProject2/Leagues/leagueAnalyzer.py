from Leagues.leagueAccessor import *
from Players.player import Player
from Players.playerAccessor import *
from Teams.teamAccessor import TeamAccessor, get_team_object_by_key, get_team_roster
from YahooLeague import YahooLeague
from DataBase import DataBase as db


def league_ranking(season_stats, league: League):
    ranked_df = league_stats(season_stats, league)
    for i in ranked_df.columns:
        if i != 'league_id' and i != 'team_key' and i != 'team_name':
            if i != 'current_TOV' and i != 'last_TOV':
                ranked_df[i] = ranked_df[i].rank(ascending=False, ).astype(int)
            else:
                ranked_df[i] = ranked_df[i].rank(ascending=True, ).astype(int)

    return ranked_df


def analyze_matchup(league: League):
    yl = YahooLeague(league.league_id)
    df = pd.DataFrame(yl.league_yahoo.matchups())
    bn = pd.DataFrame(df.fantasy_content.values.tolist()[1])['scoreboard']
    df_matchup = pd.DataFrame(columns=db.STATS_FOR_MATCHUP.split(','))
    count_row = 0
    count_col = 0
    try:
        for i in bn[1]['0']['matchups'].values():

            for j in (i['matchup']['0']['teams']).values():
                try:
                    df_matchup.loc[count_row] = [None] * len(df_matchup.columns)

                    team_name = j['team'][0][2]['name']
                    df_matchup.iat[count_row, count_col] = team_name
                    for k in (j['team'][1]['team_stats']['stats']):
                        count_col += 1
                        df_matchup.iat[count_row, count_col] = k['stat']['value']

                    count_row += 1
                    count_col = 0
                except TypeError:

                    continue

    except TypeError:
        pass
    # Call the recursive function with the JSON data
    return df_matchup


def matchup_analyzer(week_num, league: League):
    columns_name = db.CURRENT_FANTASY_CAT.split(',')
    league = YahooLeague(league.league_id)
    my_team = league.team_key()
    my_count = 0
    my_total_games = 0
    team = Team(TeamAccessor.get_team_object_by_key(my_team))
    my_roster = get_team_roster(team)

    my_team_df = pd.DataFrame(columns=columns_name)
    for my_name in my_roster:
        player = Player(*get_player_object(my_name))
        my_team_name = get_player_nba_team(player)
        if league.is_injuerd(player.player_name) is False:
            my_count += 1
            db.cursor.execute(PlayerAccesor.GAMES_IN_MATCHUP, (week_num, my_team_name, my_team_name,))
            my_count_games_in_matchup = db.cursor.fetchall()
            my_total_games += my_count_games_in_matchup[0][0]
            db.cursor.execute(PlayerAccesor.GET_PLAYER_STATS, (my_name[0],))
            pg_player_stats = db.cursor.fetchall()
            stat_mult_in_games = [my_count_games_in_matchup[0][0] * pg_player_stats[0][i] for i in range(0, 13) if
                                  i != 2 or i != 5]
            my_team_df.loc[len(my_team_df)] = stat_mult_in_games

    ## opponet week
    opp_count = 0
    opp_total_games = 0
    opp_team_key = league.get_matchup(week_num)
    opp_team = Team(*get_team_object_by_key(opp_team_key))
    opp_roster = get_team_roster(opp_team)
    opp_team_df = pd.DataFrame(columns=columns_name)
    for opp_name in opp_roster:
        opp_player = Player(*get_player_object(opp_name))

        opp_team_name = get_player_nba_team(opp_player)
        if league.is_injuerd(opp_name[0]) is False:
            opp_count += 1
            db.cursor.execute(PlayerAccesor.GAMES_IN_MATCHUP, (week_num, opp_team_name[0][0], opp_team_name[0][0]))
            opp_count_games_in_matchup = db.cursor.fetchall()
            opp_total_games += opp_count_games_in_matchup[0][0]
            db.cursor.execute(PlayerAccesor.GET_PLAYER_STATS, (opp_name[0],))
            pg_player_stats_opp = db.cursor.fetchall()
            stat_mult_in_games_opp = [opp_count_games_in_matchup[0][0] * pg_player_stats_opp[0][i] for i in range(0, 13)
                                      if i != 2 or i != 5]
            opp_team_df.loc[len(opp_team_df)] = stat_mult_in_games_opp

    final_df = pd.DataFrame([my_team_df.sum(), opp_team_df.sum()], columns=db.CURRENT_FANTASY_CAT.split(','))
    final_df = final_df.rename(index={0: team.team_name, 1: opp_team.team_name})
    final_df.at[team.team_name, 'current_FT_PCT'] = final_df.at[
                                                        team.team_name, 'current_FT_PCT'] / my_total_games
    final_df.at[team.team_name, 'current_FG_PCT'] = final_df.at[
                                                        team.team_name, 'current_FG_PCT'] / my_total_games
    final_df.at[opp_team.team_name, 'current_FT_PCT'] = final_df.at[
                                                            opp_team.team_name, 'current_FT_PCT'] / opp_total_games
    final_df.at[opp_team.team_name, 'current_FG_PCT'] = final_df.at[
                                                            opp_team.team_name, 'current_FG_PCT'] / opp_total_games
    return final_df
