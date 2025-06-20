from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.endpoints import commonplayerinfo


## for only single player
class PlayerAnalyzer:

    def __init__(self, full_name):

        self.stats_by_last_season = None
        self.stats_by_career = None
        self.nba_players = players.get_players()

        # self.player_info = [player for player in self.nba_players if player["full_name"] == full_name][0]

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

    def career_stats(self):
        if self.player_info is None:
            return None
        else:
            self.stats_by_career = playercareerstats.PlayerCareerStats(player_id=self.get_id())
            return self.stats_by_career.get_data_frames()[0]

    def last_season_stats(self):
        if self.player_info is None:
            return None
        else:
            self.stats_by_last_season = self.career_stats()[self.career_stats()['SEASON_ID'] == '2022-23']
            return self.stats_by_last_season

    def adj_fantasy(self):
        if self.player_info is None:
            return None
        else:
            selected_columns_from_last_season = self.last_season_stats()[
                ['SEASON_ID', 'TEAM_ABBREVIATION', 'GP', 'FG_PCT', 'FT_PCT', 'FG3M', 'PTS', 'REB', 'AST', 'STL', 'BLK',
                 'TOV']].copy()
            if len(selected_columns_from_last_season) <= 1:
                # for rookies or players who played for 1 team
                return selected_columns_from_last_season
            else:
                # for players who played in more than 1 team
                total_selected = selected_columns_from_last_season[
                    selected_columns_from_last_season['TEAM_ABBREVIATION'] == 'TOT']
                return total_selected

    def pg_adj_fantasy(self):

        pg_adj = self.adj_fantasy()
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
