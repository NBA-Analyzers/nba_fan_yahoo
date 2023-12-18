from datetime import datetime

from Leagues.league import League
from Leagues.leagueAnalyzer import analyze_matchup
from Players.playerAnalyzer import *
import pandas as pd

from Players.playerAnalyzer import _rename_players
from YahooLeague import YahooLeague
from DataBase import DataBase as db
from Teams.teamAccessor import get_team_stats, team_size, pg_avg_stats_team, get_team_object, get_team_roster
from Players.playerAccessor import get_list_of_players_stats, get_player_object, get_player_nba_team
from Teams.team import Team
from Players.player import Player


class TeamAnalyzer:
    ## get team roster
    TEAM_ROSTER_SQL = "select player_name FROM dbo.team_player where team_name = ?"
    ## get team name and stats
    TEAM_SQL = f"Select team_name, {db.ALL_FANTASY_CAT} FROM dbo.league_teams where team_name = ? "
    ## count players in roster
    COUNT_PLAYERS_IN_ROSTER = "select count(*) FROM dbo.team_player where team_name = ?"
    ## new player and old player name and stats
    PLAYERS_SQL = f"Select full_name, {db.ALL_FANTASY_CAT} FROM dbo.nba_players p where full_name = ? or full_name = ?"
    ## get team stats
    TEAM_STATS_QUERY = f"select {db.CURRENT_FANTASY_CAT} from dbo.yahoo_league_teams where team_name = ?"
    ## search all games within the same week after the date
    later_date = "SELECT count(*) FROM dbo.schedule WHERE week_number = ? AND " \
                 "CONVERT(DATE, game_date, 101) >= CONVERT(DATE,?, 101) " \
                 "and (dbo.schedule.home_team=? or  dbo.schedule.away_team=?)"
    ## get player curent stats
    get_player_current_stats = f"select {db.CURRENT_FANTASY_CAT} from dbo.players where player_name=?"


# only for current year
def sub_player_effect(old_players, new_players, team, season_stats):
    yl = YahooLeague(team.league_id)
    without_old_players = 0
    with_new_players = 0
    team_stats = (pg_avg_stats_team(season_stats, team, yl))
    old_players_stats = get_list_of_players_stats(old_players)
    new_players_stats = get_list_of_players_stats(new_players)
    for i, j in zip(old_players_stats, new_players_stats):
        print(i)
        without_old_players = [round(x - y, 3) for x, y in zip(team_stats.values.tolist()[0], i)]
        with_new_players = [round(x + y, 3) for x, y in zip(without_old_players, j)]
    with_new_players[2] = round(with_new_players[0] / with_new_players[1], 3)
    with_new_players[5] = round(with_new_players[3] / with_new_players[4], 3)
    sum_of_old_players = [round(sum(x), 3) for x in zip(*old_players_stats)]
    sum_of_new_players = [round(sum(x), 3) for x in zip(*new_players_stats)]
    ## prints the differnce between the players and the team including them
    df_player_comparison = pd.DataFrame([sum_of_new_players, sum_of_old_players],
                                        columns=db.FANTASY_CAT_STATS.split(',')).rename(
        index={0: 'new players', 1: 'old players'})
    df_teams_comparison = pd.DataFrame([with_new_players, team_stats.values.tolist()[0]],
                                       columns=db.FANTASY_CAT_STATS.split(',')).rename(
        index={0: 'new team stats', 1: 'old team stats'})
    print('The change for your team in each category')
    for j in range(0, 13):
        print(
            f' change in {df_teams_comparison.columns[j]} is {(with_new_players[j] - team_stats.values.tolist()[0][j]):.3f} ')
    return df_player_comparison, df_teams_comparison


def get_matchup_of_team(team: Team):
    league = League(team.league_id, team.league_name)
    cur_df = analyze_matchup(league)
    row_of_team = cur_df.loc[cur_df['NAME'] == team.team_name].index.to_numpy()[0]
    if row_of_team % 2 == 0:
        matchup_name = cur_df.loc[row_of_team + 1, 'NAME']
    else:

        matchup_name = (cur_df.loc[row_of_team - 1, 'NAME'])
    return matchup_name


def current_result_of_matchup(team: Team):
    league = League(team.league_id, team.league_name)
    past_matchup = analyze_matchup(league)
    opp_team = get_matchup_of_team(team)
    my_team_past_matchup = past_matchup[past_matchup['NAME'] == team.team_name]
    opp_team_past_matchup = past_matchup[past_matchup['NAME'] == opp_team]
    result_past_matchup = pd.concat([my_team_past_matchup,opp_team_past_matchup])
    return result_past_matchup
def projected_matchup(team: Team):
    opp_team = Team(*get_team_object(get_matchup_of_team(team)))
    yl = YahooLeague(team.league_id)
    df = pd.DataFrame(yl.lg.matchups())
    league_set = (df.fantasy_content.values.tolist()[1][0])
    week_number = league_set['current_week']
    current_date = league_set['edit_key']
    converted_date = datetime.strptime(current_date, '%Y-%m-%d').strftime('%m/%d/%Y')

    columns_name = db.CURRENT_FANTASY_CAT.split(',')
    games_count = 0
    cur_team_df = pd.DataFrame(columns=columns_name)
    final_df = pd.DataFrame()
    total_games_in_matchup = 0
    for m in range(2):
        if m == 0:
            cur_team_roster = get_team_roster(team)
        else:
            cur_team_df = pd.DataFrame(columns=columns_name)
            cur_team_roster = get_team_roster(opp_team)
        for full_name in cur_team_roster:
            full_name = _rename_players(full_name)
            player = Player(*get_player_object(full_name))
            if yl.is_injuerd(player.player_name) is False:
                nba_team = get_player_nba_team(player)
                try:
                    db.cursor.execute(TeamAnalyzer.later_date, (week_number, converted_date, nba_team, nba_team,))
                    games_in_schedule = db.cursor.fetchall()
                    total_games_in_matchup += games_in_schedule[0][0]
                except IndexError:
                    continue
                db.cursor.execute(TeamAnalyzer.get_player_current_stats, (player.player_name,))
                pg_player_stats_opp = db.cursor.fetchall()
                total_stat_player = [games_in_schedule[0][0] * pg_player_stats_opp[0][j] for j in range(0, 13)]

                cur_team_df.loc[len(cur_team_df)] = total_stat_player
        row_sum = cur_team_df.sum()
        row_sum.at['current_FG_PCT'] = row_sum.at['current_FG_PCT'] / total_games_in_matchup
        row_sum.at['current_FT_PCT'] = row_sum.at['current_FT_PCT'] / total_games_in_matchup
        final_df = pd.concat([final_df, row_sum.to_frame().transpose()], ignore_index=True)
        # final_df = final_df.rename(index={0: my_yahoo_team[0][0], 1: opp_yahoo_team[0][0]})
        total_games_in_matchup = 0
    return final_df.rename(index={0: team.team_name, 1: opp_team.team_name})


def combine_match(team: Team):
    league = League(team.league_id, team.league_name)
    past_matchup = analyze_matchup(league)
    projected_matchup_arg = projected_matchup(team)
    opp_team = get_matchup_of_team(team)
    my_team_past_matchup = past_matchup[past_matchup['NAME'] == team.team_name]
    opp_team_past_matchup = past_matchup[past_matchup['NAME'] == opp_team]

    for col in projected_matchup_arg:
        if col in my_team_past_matchup:
            try:
                projected_matchup_arg.loc[team.team_name, col] = float(projected_matchup_arg.loc[team.team_name, col]) + \
                                                                 float(my_team_past_matchup[col].iloc[0])
                projected_matchup_arg.loc[opp_team, col] = float(projected_matchup_arg.loc[opp_team, col]) + \
                                                           float(opp_team_past_matchup[col].iloc[0])
            except KeyError:
                continue
    try:
        projected_matchup_arg.loc[team.team_name, 'current_FGM'] = projected_matchup_arg.loc[
                                                                       team.team_name, 'current_FGM'] + float(
            my_team_past_matchup['FGM/A'].iloc[0].split('/')[0])
        projected_matchup_arg.loc[team.team_name, 'current_FGA'] = projected_matchup_arg.loc[
                                                                       team.team_name, 'current_FGA'] + float(
            my_team_past_matchup['FGM/A'].iloc[0].split('/')[1])
        projected_matchup_arg.loc[opp_team, 'current_FGM'] = projected_matchup_arg.loc[opp_team, 'current_FGM'] + float(
            opp_team_past_matchup['FGM/A'].iloc[0].split('/')[0])
        projected_matchup_arg.loc[opp_team, 'current_FGA'] = projected_matchup_arg.loc[opp_team, 'current_FGA'] + float(
            opp_team_past_matchup['FGM/A'].iloc[0].split('/')[1])

    except KeyError:
        pass
    try:
        projected_matchup_arg.loc[team.team_name, 'current_FTM'] = projected_matchup_arg.loc[
                                                                       team.team_name, 'current_FTM'] + float(
            my_team_past_matchup['FTM/A'].iloc[0].split('/')[0])
        projected_matchup_arg.loc[team.team_name, 'current_FTA'] = projected_matchup_arg.loc[
                                                                       team.team_name, 'current_FTA'] + float(
            my_team_past_matchup['FTM/A'].iloc[0].split('/')[1])
        projected_matchup_arg.loc[opp_team, 'current_FTM'] = projected_matchup_arg.loc[opp_team, 'current_FTM'] + float(
            my_team_past_matchup['FTM/A'].iloc[0].split('/')[0])
        projected_matchup_arg.loc[opp_team, 'current_FTA'] = projected_matchup_arg.loc[opp_team, 'current_FTA'] + float(
            opp_team_past_matchup['FTM/A'].iloc[0].split('/')[1])
    except KeyError:
        pass
    projected_matchup_arg.loc[team.team_name, 'current_FG_PCT'] = projected_matchup_arg.loc[
                                                                      team.team_name, 'current_FGM'] / \
                                                                  projected_matchup_arg.loc[
                                                                      team.team_name, 'current_FGA']
    projected_matchup_arg.loc[team.team_name, 'current_FT_PCT'] = projected_matchup_arg.loc[
                                                                      team.team_name, 'current_FTM'] / \
                                                                  projected_matchup_arg.loc[
                                                                      team.team_name, 'current_FTA']
    projected_matchup_arg.loc[opp_team, 'current_FG_PCT'] = projected_matchup_arg.loc[
                                                                opp_team, 'current_FGM'] / \
                                                            projected_matchup_arg.loc[
                                                                opp_team, 'current_FGA']
    projected_matchup_arg.loc[opp_team, 'current_FT_PCT'] = projected_matchup_arg.loc[
                                                                opp_team, 'current_FTM'] / \
                                                            projected_matchup_arg.loc[
                                                                opp_team, 'current_FTA']

    return projected_matchup_arg
