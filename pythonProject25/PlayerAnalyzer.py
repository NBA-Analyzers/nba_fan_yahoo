from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.endpoints import commonplayerinfo


## for only single player
class PlayerAnalyzer:
    players_dict_helper = {"Xavier Tillman Sr.": "Xavier Tillman", "P.J. Washington Jr.": "P.J. Washington"
                           }

    def __init__(self, full_name):

        self.nba_players = players.get_players()

        if full_name in PlayerAnalyzer.players_dict_helper:
            full_name = PlayerAnalyzer.players_dict_helper[full_name]

        matching_players = [player for player in self.nba_players if player["full_name"] == full_name]
        if matching_players:
            self.player_info = matching_players[0]
            # Do something with player_id
        else:
            self.player_info = None

    def get_id(self):
        if self.player_info is None:
            return None
        else:
            return self.player_info['id']

    def get_player_nba_team(self):
        if self.player_info is None:
            return None
        else:
            nba_team_abb = self.current_season_stats()['TEAM_ABBREVIATION'].iloc[0]
            nba_team = teams.find_team_by_abbreviation(nba_team_abb)
            return nba_team['nickname']

    def career_stats(self):
        if self.player_info is None:
            return None
        else:
            stats_by_career = playercareerstats.PlayerCareerStats(player_id=self.get_id())
            return stats_by_career.get_data_frames()[0]

    def current_season_stats(self):
        if self.player_info is None:
            return None
        else:
            stats_by_current_season = self.career_stats()[self.career_stats()['SEASON_ID'] == '2023-24']
            return stats_by_current_season

    def last_season_stats(self):
        if self.player_info is None:
            return None
        else:
            stats_by_last_season = self.career_stats()[self.career_stats()['SEASON_ID'] == '2022-23']
            return stats_by_last_season

    def adj_fantasy(self, season_stats):
        if self.player_info is None:
            return None
        else:
            if season_stats == '2023-24':
                selected_columns_from_current_season = self.current_season_stats()[
                    ['SEASON_ID', 'TEAM_ABBREVIATION', 'GP', 'FGM', 'FGA', 'FG_PCT', 'FTM', 'FTA', 'FT_PCT', 'FG3M',
                     'PTS',
                     'REB', 'AST', 'STL', 'BLK',
                     'TOV']].copy()
                if len(selected_columns_from_current_season) <= 1:
                    # for rookies or players who played for 1 team
                    return selected_columns_from_current_season
                else:
                    # for players who played in more than 1 team
                    total_selected = selected_columns_from_current_season[
                        selected_columns_from_current_season['TEAM_ABBREVIATION'] == 'TOT']
                    return total_selected

            else:
                selected_columns_from_last_season = self.last_season_stats()[
                    ['SEASON_ID', 'TEAM_ABBREVIATION', 'GP', 'FGM', 'FGA', 'FG_PCT', 'FTM', 'FTA', 'FT_PCT', 'FG3M',
                     'PTS',
                     'REB', 'AST', 'STL', 'BLK',
                     'TOV']].copy()
                if len(selected_columns_from_last_season) <= 1:
                    # for rookies or players who played for 1 team
                    return selected_columns_from_last_season
                else:
                    # for players who played in more than 1 team
                    total_selected = selected_columns_from_last_season[
                        selected_columns_from_last_season['TEAM_ABBREVIATION'] == 'TOT']
                    return total_selected

    def pg_adj_fantasy(self, season_stats):

        pg_adj = self.adj_fantasy(season_stats)
        for col in pg_adj.columns:

            if col != 'SEASON_ID' and col != 'TEAM_ABBREVIATION' and col != 'GP' and col != 'FT_PCT' and col != 'FG_PCT':
                try:
                    pg_adj[col] = float(pg_adj[col]) / float(pg_adj['GP'])
                except TypeError:
                    continue
        return pg_adj

    def is_rookie(self):
        try:
            player_info = commonplayerinfo.CommonPlayerInfo(player_id=self.get_id())
            player_info = player_info.get_data_frames()[0]
        except ValueError:
            return True
        # Extract the rookie year
        rookie_year = player_info['DRAFT_YEAR'].iloc[0]

        # Check if the player's rookie year is the same as the current season
        return rookie_year == '2023'
