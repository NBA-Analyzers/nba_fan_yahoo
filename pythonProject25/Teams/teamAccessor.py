import pandas as pd
from nba_api.stats.static import players
import pyodbc

from Players.player import Player
from Players.playerAccessor import pg_adj_fantasy

import yahoo_fantasy_api as yfa
from Teams.team import Team
from YahooLeague import YahooLeague
from DataBase import DataBase as db,find_last_year,find_current_year


class TeamAccessor(object):
    # data = {'FGM': 0, 'FGA': 0, 'FG_PCT': [0], 'FTM': 0, 'FTA': 0, 'FT_PCT': [0], 'FG3M': [0], 'PTS': [0],
    #         'REB': [0], 'AST': [0], 'STL': [0], 'BLK': [0],
    #         'TOV': [0]}
    TEAM_LENGTH = 0
    ## get team name and stats
    team_stats_query = f"Select  {db.ALL_FANTASY_CAT} FROM dbo.league_teams where team_name = ? "
    get_team_roster_by_team_key = "select player_name from dbo.teams_player where team_key =?"


def pg_avg_stats_team(season_stats, team: Team):
    yl = YahooLeague(team.league_id)
    team_roster = yl.get_team(team.team_key, True)
    # team_total_df = pd.DataFrame(TeamAccessor.data)
    # df_fantasy_cat = pd.DataFrame(TeamAccessor.data)
    team_total_df = pd.DataFrame(columns=db.FANTASY_CAT_STATS.split(','))
    df_fantasy_cat = pd.DataFrame(columns=db.FANTASY_CAT_STATS.split(','))
    list_team_roster = [i['name'] for i in team_roster]

    for player_info in players.get_active_players():
        if player_info['full_name'] in list_team_roster:
            player = Player(player_info['full_name'], player_info['id'])
            temp_df = pg_adj_fantasy(season_stats, player, True)
            if temp_df.empty or yl.is_injuerd(player_info['full_name']):
                continue
            TeamAccessor.TEAM_LENGTH += 1
            df_fantasy_cat = pg_adj_fantasy(season_stats, player, True)

        for column in team_total_df.columns:
            if column in df_fantasy_cat.columns:
                try:
                    team_total_df.at[TeamAccessor.TEAM_LENGTH - 1, column] = float(df_fantasy_cat[column])
                except TypeError:
                    continue

    total_team = team_total_df.sum()
    total_team['FG_PCT'] = total_team['FGM'] / total_team['FGA']
    total_team['FT_PCT'] = total_team['FTM'] / total_team['FTA']

    return pd.DataFrame(data=total_team).T


def pg_team_stats(season_stats, team: Team, from_api=False):
    if from_api:
        stats = pg_avg_stats_team(season_stats, team)
        pg_play_stats = pd.DataFrame(stats / TeamAccessor.TEAM_LENGTH)
        pg_play_stats['FG_PCT'] = pg_play_stats['FG_PCT'] * TeamAccessor.TEAM_LENGTH
        pg_play_stats['FT_PCT'] = pg_play_stats['FT_PCT'] * TeamAccessor.TEAM_LENGTH

    else:
        db.cursor.execute(TeamAccessor.team_stats_query, (team.team_name,))
        df_of_sql = db.cursor.fetchall()
        pg_play_stats = pd.DataFrame(db.FANTASY_CAT_STATS)
        col = 0
        for i in pg_play_stats.columns:
            pg_play_stats.loc[0, i] = df_of_sql[0][col]
            col += 1
    return pg_play_stats

    ### insert all the teams from al the leagues I am in, into the table yahoo_league_teams


def get_team_new_stats(team, season_stats):
    curr_player_stats = pg_adj_fantasy(season_stats, team, True)
    all_current_stats = [curr_player_stats[stat].iloc[0].round(3) for stat in db.FANTASY_CAT_STATS]

    return {all_current_stats}


## get team roster by team_key
def get_team(team_key, from_api=False):
    if from_api:
        cur_team = yfa.team.Team(db.sc, team_key)
        team_roster = cur_team.roster()

    else:
        db.cursor.execute(TeamAccessor.get_team_roster_by_team_key, (team_key,))
        team_roster = db.cursor.fetchall()
    return team_roster


def sync_teams_to_database(commit_count=0):
    # insert from scratch

    insert_query_league = f"INSERT INTO yahoo_league_teams (team_key,team_name,league_name,{db.ALL_FANTASY_CAT}) VALUES (?, ?, ?, ?, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"

    for league_id in db.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = db.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:

                team = Team(cur_teams[team_key]['team_key'], cur_teams[team_key]['name'], cur_league.settings()['name'],
                            league_id)
                cur_team_stats = pg_team_stats(find_current_year(), team, True)
                last_team_stats = pg_team_stats(find_last_year(), team, True)

                data = (team.team_key, team.team_name, team.league_name,
                        *cur_team_stats.iloc[0].tolist(), * last_team_stats.iloc[0].tolist())
                print(team.team_name)
                db.cursor.execute(insert_query_league, data)

                commit_count += 1

                if commit_count >= 10:
                    db.connection.commit()
                    commit_count = 0
    if commit_count > 0:
        db.connection.commit()

    db.connection.commit()

    # Close the cursor and connection
    db.cursor.close()
    db.connection.close()


def update_league_teams_db(commit_count=0):
    update_query_teams = f"UPDATE league_teams " \
                         f"SET {db.ALL_FANTASY_CAT} WHERE league_id = ? AND team_key = ? "
    affected_rows = 0
    for league_id in db.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = db.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()

            for team_key in cur_teams:
                team = Team(league_id, cur_teams[team_key]['team_key'], cur_teams[team_key]['name'],
                            cur_league.settings()['name'])
                cur_team_stats = get_team_new_stats(find_current_year(), team)
                last_team_stats = get_team_new_stats(find_last_year(), team)

                data = (
                    {cur_team_stats}, {last_team_stats}, league_id,
                    team_key
                )
                print(cur_teams[team_key]['name'])
                affected_rows = db.cursor.execute(update_query_teams, data).rowcount
                commit_count += 1
                if commit_count >= 10:
                    db.connection.commit()
                    commit_count = 0

    if commit_count > 0:
        db.connection.commit()
    print(affected_rows)
    # Close the cursor and connection
    db.cursor.close()
    db.connection.close()
