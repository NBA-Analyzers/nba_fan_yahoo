from Players.playerAnalyzer import PlayerAnalyzer
import pandas as pd
from YahooLeague import YahooLeague
from DataBase import DataBase as db

class TeamAnalyzer:
    ## get team roster
    team_roster_sql = "select player_name FROM dbo.team_player where team_name = ?"
    ## get team name and stats
    team_sql = f"Select team_name, {db.ALL_FANTASY_CAT} FROM dbo.league_teams where team_name = ? "
    ## count players in roster
    count_players_in_roster = "select count(*) FROM dbo.team_player where team_name = ?"
    ## new player and old player name and stats
    players_sql = f"Select full_name, {db.ALL_FANTASY_CAT} FROM dbo.nba_players p where full_name = ? or full_name = ?"
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

def sub_player_effect(old_player, new_player, team_name):
    db.cursor.execute(TeamAnalyzer.team_roster_sql, (team_name,))
    team_roster_list = db.cursor.fetchall()[0:]

    in_roster = False
    for i in team_roster_list:
        if old_player == i[0]:
            in_roster = True
    if not in_roster:
        raise ValueError(f"{old_player} is not in {team_name}")
    else:

        db.cursor.execute(TeamAnalyzer.team_sql, (team_name,))
        team_stat = db.cursor.fetchall()

        db.cursor.execute(TeamAnalyzer.count_players_in_roster, (team_name,))
        roster_len = db.cursor.fetchall()

        db.cursor.execute(TeamAnalyzer.players_sql, (old_player, new_player,))
        players_stat = db.cursor.fetchall()

        if players_stat[0][0] == old_player:
            old_player_stat = players_stat[0]
            new_player_stat = players_stat[1]
        else:
            old_player_stat = players_stat[1]
            new_player_stat = players_stat[0]

        new_team_stats = []
        for i in range(1, 14):
            try:
                new_team_stats.append(
                    float(
                        f"{(team_stat[0][i] * roster_len[0][0] + new_player_stat[i] - old_player_stat[i]) / 14:.3f}"))
            except AttributeError:
                continue
        ## prints the differnce between the players and the team including them
        df_players = pd.DataFrame([list(old_player_stat), list(new_player_stat)],
                                  columns=['Name'] + Tools.fantasy_cat.split(','))
        print(df_players)
        df_team = pd.DataFrame([team_stat[0][1:], new_team_stats], columns=Tools.fantasy_cat.split(','))
        print(df_team.rename(index={0: 'old team stats', 1: 'new team stats'}))
        ## prints the change in each category
        list_of_cat = Tools.fantasy_cat.split(',')
        print('The change for your team in each category')
        for j in range(0, 13):
            print(f' change in {list_of_cat[j]} is {(new_team_stats[j] - team_stat[0][j + 1]):.3f} ')

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


