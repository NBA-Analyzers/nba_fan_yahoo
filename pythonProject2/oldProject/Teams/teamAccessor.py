import pandas as pd
from nba_api.stats.static import players
import pyodbc

from Players.player import Player
from Players.playerAccessor import pg_adj_fantasy

import yahoo_fantasy_api as yfa
from Teams.team import Team
from pythonProject2.oldProject.YahooLeague import YahooLeague
from pythonProject2.oldProject.DataBase import DataBase as db, find_last_year, find_current_year


class TeamAccessor(object):
    TEAM_LENGTH = 0
    CURRENT_TEAM_STATS_QUERY = f"Select {db.CURRENT_FANTASY_CAT} FROM dbo.yahoo_league_teams where team_name = ? "
    LAST_TEAM_STATS_QUERY = f"Select {db.LAST_SEASON_FANTASY_CAT} FROM dbo.yahoo_league_teams where team_name = ? "
    GET_TEAM_ROSTER_BY_TEAM_KEY = "select player_name from dbo.team_players where team_key =?"
    GET_TEAM_OBJECT_QUERY = "select team_key,team_name,tm.league_name, league_id from dbo.yahoo_league_teams tm join dbo.leagues lg on lg.league_name = tm.league_name where team_name = ?"
    GET_TEAM_OBJECT_BY_KEY_QUERY = "select team_key,team_name,tm.league_name, league_id from dbo.yahoo_league_teams tm join dbo.leagues lg on lg.league_name = tm.league_name where team_key = ?"

    @staticmethod
    def get_team_object_by_key(team_key):
        db.cursor.execute(TeamAccessor.GET_TEAM_OBJECT_BY_KEY_QUERY, (team_key,))
        team_object = db.cursor.fetchall()
        return team_object[0]

    @staticmethod
    def get_team_object(team_name):
        db.cursor.execute(TeamAccessor.GET_TEAM_OBJECT_QUERY, (team_name,))
        team_object = db.cursor.fetchall()
        return team_object[0]

    @staticmethod
    def get_team_roster(team, from_api=False):
        if from_api:
            cur_team = yfa.team.Team(db.sc, team.team_key)
            team_roster_info = cur_team.roster()
            team_roster = [i['name'] for i in team_roster_info]
        else:
            get_team_roster_by_team_key = "select player_name from dbo.team_players where team_key =?"
            db.cursor.execute(get_team_roster_by_team_key, (team.team_key,))
            team_roster_query = db.cursor.fetchall()
            team_roster = [i[0] for i in team_roster_query]
        return team_roster

    @staticmethod
    def team_size(team: Team, yl, from_api=False):
        team_length = 0
        team.roster = TeamAccessor.get_team_roster(team,from_api)

        if team.roster is not None:
            for i in team.roster:
                if yl.is_injuerd(i) is False:
                    team_length += 1
                    
        return team_length


## per game stats of all the team
def pg_avg_stats_team(season_stats, team: Team, yl):
    team.roster = TeamAccessor.get_team_roster(team, True)
    team_total_df = pd.DataFrame(columns=db.FANTASY_CAT_STATS.split(','))

    for player_info in players.get_active_players():
        if player_info['full_name'] in team.roster:
            player = Player(player_info['full_name'], player_info['id'])
            player.stats = pg_adj_fantasy(season_stats, player, True)
            if player.stats.empty or yl.is_injuerd(player.player_name):
                continue
            TeamAccessor.TEAM_LENGTH += 1
            for column in team_total_df.columns:
                if column in player.stats.columns:
                    try:
                        team_total_df.at[TeamAccessor.TEAM_LENGTH - 1, column] = float(player.stats[column])
                    except TypeError:
                        continue

    total_team = team_total_df.sum()
    total_team['FG_PCT'] = total_team['FGM'] / total_team['FGA']
    total_team['FT_PCT'] = total_team['FTM'] / total_team['FTA']

    return pd.DataFrame(data=total_team).T


### per game stats of team divided by how much players in team
def pg_team_stats(season_stats, team: Team, from_api=False):
    if from_api:
        yl = YahooLeague(team.league_id)
        stats = pg_avg_stats_team(season_stats, team, yl).round(3)
        pg_play_stats = pd.DataFrame(stats / TeamAccessor.team_size(team, yl, True))
        pg_play_stats['FG_PCT'] = pg_play_stats['FG_PCT'] * TeamAccessor.TEAM_LENGTH
        pg_play_stats['FT_PCT'] = pg_play_stats['FT_PCT'] * TeamAccessor.TEAM_LENGTH

    else:
        if season_stats == find_current_year():
            db.cursor.execute(TeamAccessor.CURRENT_TEAM_STATS_QUERY, (team.team_name,))
            data_from_sql = db.cursor.fetchall()
            pg_play_stats = pd.DataFrame.from_records([data_from_sql[0]], columns=db.CURRENT_FANTASY_CAT.split(','))
        else:
            db.cursor.execute(TeamAccessor.LAST_TEAM_STATS_QUERY, (team.team_name,))
            data_from_sql = db.cursor.fetchall()
            pg_play_stats = pd.DataFrame.from_records([data_from_sql[0]], columns=db.LAST_SEASON_FANTASY_CAT.split(','))

    return pg_play_stats

    ### insert all the teams from al the leagues I am in, into the table yahoo_league_teams


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
                team.current_stats = pg_team_stats(find_current_year(), team, True)
                team.last_stats = pg_team_stats(find_last_year(), team, True)

                data = (team.team_key, team.team_name, team.league_name,
                        *team.current_stats.iloc[0].tolist(), *team.last_stats.iloc[0].tolist())
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


def update_league_teams_db(commit_count=0,count=0):
    set_clause = ', '.join([f"{column} = ?" for column in db.ALL_FANTASY_CAT.split(',')])

    update_query_teams = f"UPDATE yahoo_league_teams " \
                         f"SET team_name=?,{set_clause} " \
                         f"WHERE  team_key = ? "
    affected_rows = 0
    for league_id in db.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = db.yahoo_game.to_league(league_id)  # do it to get the teams in the league in the next row
            cur_teams = cur_league.teams()

            for team_key in cur_teams:
                count+=1
                if count>20:
                    team = Team(cur_teams[team_key]['team_key'], cur_teams[team_key]['name'],
                                cur_league.settings()['name'], league_id)
                    team.current_stats = pg_team_stats(find_current_year(), team, True)
                    team.last_stats = pg_team_stats(find_last_year(), team, True)

                    data = (team.team_name,
                            *team.current_stats.iloc[0].tolist(), *team.last_stats.iloc[0].tolist(),
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


## get team stats as list
def get_team_stats(my_team_name):
    ## get team stats

    db.cursor.execute(TeamAccessor.CURRENT_TEAM_STATS_QUERY, (my_team_name,))
    team_roster_stats = db.cursor.fetchall()
    return team_roster_stats[0]
