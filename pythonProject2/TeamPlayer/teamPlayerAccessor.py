### insert all the players in all the leagues I am in into team_player table
from nba_api.stats.library.data import players

from DataBase import DataBase
from Players.player import Player
from YahooLeague import YahooLeague
from Teams.team import Team
from Teams.teamAccessor import *
from Players.playerAccessor import *


class TeamPlayerAccessor(object):
    INSERT_QUERY_TEAM_PLAYER = "INSERT INTO team_players (team_player_id, team_key, player_id,player_name, team_name," \
                               "league_name) " \
                               "VALUES ( ?, ?,?, ?,?,?) "
    UPDATE_QUERY_TEAM_PLAYER = "Update team_players SET  team_key=?, player_id=?,player_name=?, team_name=?," \
                               "league_name=? WHERE team_player_id=? "


def team_player_to_database(update=False, commit_count=0, player_count=0):

    for league_id in DataBase.yahoo_game.league_ids():
        if league_id[0:3] == "428":
            cur_league = DataBase.yahoo_game.to_league(league_id)
            cur_teams = cur_league.teams()
            lg = YahooLeague(league_id)

            for team in cur_teams:
                yahoo_team = Team(team, cur_teams[team]['name'], lg.league_name(), league_id)
                team_roster = get_team_roster(yahoo_team, True)
                for player in team_roster:
                    player_id = get_player_id(player)
                    nba_player = Player(player, player_id)
                    player_count += 1
                    print(nba_player.player_name, yahoo_team.league_name)
                    if update:
                        data = (yahoo_team.team_key, nba_player.player_id, nba_player.player_name
                                , yahoo_team.team_name, yahoo_team.league_name, player_count)
                        DataBase.cursor.execute(TeamPlayerAccessor.UPDATE_QUERY_TEAM_PLAYER, data)
                    else:
                        data = (player_count, yahoo_team.team_key, nba_player.player_id, nba_player.player_name
                                , yahoo_team.team_name, yahoo_team.league_name)
                        DataBase.cursor.execute(TeamPlayerAccessor.INSERT_QUERY_TEAM_PLAYER, data)
                    commit_count += 1
                    if commit_count >= 30:
                        DataBase.connection.commit()
                        commit_count = 0
    if commit_count > 0:
        DataBase.connection.commit()
    DataBase.cursor.close()
    DataBase.connection.close()

