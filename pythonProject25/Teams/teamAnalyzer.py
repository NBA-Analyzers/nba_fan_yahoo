from Players.playerAnalyzer import PlayerAnalyzer
import pandas as pd
from YahooLeague import YahooLeague


class TeamAnalyzer:
    def __init__(self, cur_lg, team_key):
        self.yl = YahooLeague(cur_lg)
        self.team = self.yl.get_team(team_key)
        self.length_team = len(self.team)
        data = {'FGM': 0, 'FGA': 0, 'FG_PCT': [0], 'FTM': 0, 'FTA': 0, 'FT_PCT': [0], 'FG3M': [0], 'PTS': [0],
                'REB': [0], 'AST': [0], 'STL': [0], 'BLK': [0],
                'TOV': [0]}
        self.team_total_df = pd.DataFrame(data)

    def __len__(self):
        return len(self.team)




    ### right now I dont need it

    # def pg_total_stats_team(self, season_stats, count=0):
    #
    #     for name in self.team:
    #         count += 1
    #         player_stats = PlayerAnalyzer(name['name'])
    #         fantasy_df = player_stats.pg_adj_fantasy(season_stats)
    #         if season_stats != "2023-24":
    #             if player_stats.is_rookie():
    #                 self.length_team -= 1
    #         for column in self.team_total_df.columns:
    #             if column in fantasy_df.columns:
    #                 try:
    #                     self.team_total_df.at[count, column] = float(fantasy_df[column])
    #                 except TypeError:
    #
    #                     continue
    #
    #     total_team = self.team_total_df.sum()
    #     total_team['FG_PCT'] = total_team['FGM'] / total_team['FGA']
    #     total_team['FT_PCT'] = total_team['FTM'] / total_team['FTA']
    #
    #     return pd.DataFrame(data=total_team).T
    #
    # def ps_team_stats_player(self, season_stats):
    #
    #     ps_team_stats = pd.DataFrame(self.pg_total_stats_team(season_stats) / self.length_team)
    #     ps_team_stats['FG_PCT'] = ps_team_stats['FG_PCT'] * self.length_team
    #     ps_team_stats['FT_PCT'] = ps_team_stats['FT_PCT'] * self.length_team
    #     return ps_team_stats


