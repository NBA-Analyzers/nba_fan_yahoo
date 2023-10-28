import pandas as pd
from YahooLeague import YahooLeague
from PlayerAnalyzer import PlayerAnalyzer
from TeamAnalyzer import TeamAnalyzer
from LeagueAnalyzer import LeagueAnalyzer
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import players
if __name__ == '__main__':


    ### class YahooLeague
    uri = YahooLeague('41083')
    #uri.sync_game_to_database()

    #uri.sync_league_to_database()
    uri_roster = uri.get_team('3')
    nice_uri_roster = ''
    print("=== MY Tean ===")
    print(uri_roster)
    # for r in uri_roster:
    #     nice_uri_roster += f"{r['name']}\n"
    # print(nice_uri_roster)
    # print(uri.teams_league())
    # print(len(uri))
    # print(uri.league_name())
    # print(uri.league_teams_id())
    # print(uri.get_teamkey('king douchebag'))

    ### get how much players in a team

    # team_stats = TeamAnalyzer('41083', '3')
    # team_uri = TeamAnalyzer('41083', '6')
    # print(len(team_stats))

    ### total team stats per year
    #
    #     print("=== total team stats per season ===")
    #     df_team_stats = team_stats.pg_total_stats_team()
    #     print(df_team_stats)
    #

    ### per season team stats per season

    #     print("=== total of player per season ===")
    #     df_ps_stats = team_stats.ps_team_stats_player()
    #     print(df_ps_stats)

    #### per game total stats
    # print("=== average of team per game ===")
    # df_pg_total_stats = team_stats.pg_avg_stats_team()
    # print(df_pg_total_stats)

    #### per game stat average for all players
    # print("=== average of player per game  ===")
    # df_pg_avg_stats = team_stats.pg_player_stats()
    # print(df_pg_avg_stats)
    # print("=== average of player per game Uri ===")
    # df_pg_avg_stats_uri = team_uri.pg_player_stats()
    # print(df_pg_avg_stats_uri)

    ### check PlayerAnalyzer

    # first = PlayerAnalyzer('Xavier Tillman Sr.')
    # print("ID")
    # print(first.get_id())
    # print("Career stats")
    # print(first.career_stats())
    # print("last season stats")
    # print(first.last_season_stats())
    # print("fantasy adjusted")
    # abc = first.adj_fantasy()
    # print("type", type(abc['REB']))
    # print(abc['REB'] + abc['AST'])
    # print(abc)
    # print(first.pg_adj_fantasy())
    # print(first.is_rookie())

    ### LeagueAnalyzer class

    # victorious = LeagueAnalyzer('41083')
    # print(len(victorious))
    # print(victorious.league_name())
    # print(victorious.league_Stats())
