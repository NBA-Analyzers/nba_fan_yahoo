

# from Leagues.leagueAccessor import LeagueAccessor
# from Leagues.league import League






import time

import requests


def test_team():
    ### class Team
    # team = Team('428.l.144401.t.1', 'Uri\'s Game-Changing Team', 'IFSL - Robinson League', '428.l.144401')
    # print(get_team_roster(team))
    # print(team_size(team,True))
    # print(team_size(team))
    # print(pg_avg_stats_team('2023-24', team))
    # print(pg_avg_stats_team('2022-23', team))
    # print(pg_team_stats(find_current_year(), team, True))
    # print(pg_team_stats(find_last_year(), team, True))
    # #print(team_size(team))
    # print(pg_team_stats(find_current_year(), team))
    # print(pg_team_stats('2023-24', team))
    # print(get_list_of_players_stats(['Luka Doncic', 'Kevin Durant']))
    # print(get_team_stats('Uri\'s Unmatched Team'))
    # print(sub_player_effect(['Luka Doncic', 'Kevin Durant'], ['Lebron James', 'Chris Paul'], team, find_current_year()))
    # print(get_matchup_of_team(team))
    # print(get_team_object(team.team_name))
    # print(what_categories_you_good(find_current_year(), team))
    # print(rank_what_you_good(find_current_year(),team))
    # pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # print('### matchup until now ###')
    # print(current_result_of_matchup(team))
    # print('### projected matchup """')
    # print(projected_matchup(team))
    # print('### the projected result of matchup """')
    # print(combine_match(team))
    print('a')


def test_league():
    ## class League
    # sync_leagues_to_database()
    # league = League('428.l.144401', 'Victorious Secret')
    # print(analyze_matchup(league))
    ### class League
    # sync_leagues_to_database()
    # print(sync_team_player_to_database())
    # print(get_team_stats(team.team_name))
    ### positions are PG/SG/G/SF/PF/F/C/Util
    # print(get_free_agents(league, 'Util'))
    # pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # print(league_stats(find_current_year(), league))
    # print(league_ranking(find_current_year(), league))
    # print(matchup_analyzer(8, league))
    print('a')
    
def test_stuff_todo_organize():
    # update_players_db()
    # update_league_teams_db()
    # update
    # team_player_to_database(True)
    # sync
    # team_player_to_database()
    # sync_teams_to_database()

    # print(get_best_fa_in_categories(find_current_year(), league, 'Util', ['FG3M', 'REB','AST','BLK']))
    ## Accessors
    # sync_players_to_database()
    # sync_teams_to_database()
    # sync_team_player_to_database()

    ##DataBase
    # db.cursor.execute(PlayerAccesor.GAMES_IN_MATCHUP, (8, 'Lakers',  'Lakers'))
    # my_count_games_in_matchup = db.cursor.fetchall()
    # print(my_count_games_in_matchup[0][0])
    # print(sub_player_effect(['Luka Doncic', 'Kevin Durant'], ['Lebron James', 'Chris Paul'], 'Uri\'s Unmatched Team',find_current_year()))

    ### class YahooLeague
    # uri = YahooLeague('428.l.41083')
    # print(uri.team_key())## current user team key
    # #print(uri.is_injuerd('D\'Angelo Russell'))
    # print(uri.is_injuerd('Kevin Durant'))
    # print(uri.get_matchup(3))
    #

    # # nice_uri_roster = ''
    # print("=== MY Tean ===")
    # for r in uri_roster:
    #     nice_uri_roster += f"{r['name']}\n"
    # print(nice_uri_roster)
    # print(uri.teams_league())
    # print(len(uri))
    # print(uri.league_name())
    # print(uri.league_teams_id())
    # print(uri.get_teamkey('king douchebag'))

    ### get how much players in a team

    # team_stats = TeamAnalyzer('41083', '6')
    # team_uri = TeamAnalyzer('41083', '6')
    # print(len(team_stats))

    ### total team stats per year

    # print("=== total team stats per season ===")
    # df_team_stats = team_stats.pg_total_stats_team('2023-24')
    # print(df_team_stats)
    #
    # #
    # # ### per season team stats per season
    # #
    # print("=== total of player per season ===")
    # df_ps_stats = team_stats.ps_team_stats_player('2022-23')
    # print(df_ps_stats)
    #
    # ### per game total stats
    # print("=== average of team per game ===")
    # df_pg_total_stats = team_stats.pg_avg_stats_team('2023-24')
    # print(df_pg_total_stats)

    ### per game stat average for all players
    # print("=== average of player per game  ===")
    # df_pg_avg_stats = team_stats.pg_player_stats('2023-24')
    # print(df_pg_avg_stats)
    # # df_pg_avg = team_stats.pg_avg_stats_team('2022-23')
    # # print(df_pg_avg)
    # # print("=== average of player per game Uri ===")
    # df_pg_avg_stats_uri = team_stats.pg_player_stats('2022-23')
    # print(df_pg_avg_stats_uri)
    #
    # ### check PlayerAnalyzer
    #
    # first = PlayerAnalyzer('D\'Angelo Russell')
    # print(first.get_player_nba_team())
    # print(first.current_season_stats())
    # #
    # # #print((first.current_season_stats()))
    # print(first.current_season_stats())
    # print(first.last_season_stats())
    # print(first.pg_adj_fantasy('2022-23'))
    # print(first.pg_adj_fantasy('2023-24'))
    # #print(first.adj_fantasy('2023-24'))
    # ab = first.pg_adj_fantasy('2023-24')
    #
    # print(ab)
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

    ###class DataBase

    # sync_players_to_database()
    # sync_teams_to_database()
    # sync_team_player_to_database()
    ### its important by this order
    # update_players_db()
    # update_team_player_db()
    # update_league_teams_db()

    # print(schedule_db())
    ##class Tools

    # print(search_player_in_leagues("Malik Monk"))
    # print(sub_player_effect('Gary Trent Jr.', 'Royce O\'neale', 'Uri\'s Unmatched Team'))
    # print(matchup_analyzer(3, '41083'))
    # print(league_teams_stats('41083'))
    # print(league_ranking())
    # print(matchup_week())

    ## class Advanced tools
    # at = AdvancedTools()
    # print(at.projected_matchup())
    # print(at.combine_match())
    
      ### class Playerr
    # player = Player('Chris Paul', 101108)
    # print(get_players_new_stats(player,find_current_year()))
    # print(player.full_name,player.id)
    # print(get_all_players(True))
    # print(career_stats(player))
    # print(current_season_stats(player))
    # print(last_season_stats(player))
    # print(adj_fantasy('2023-24',player))
    # print(pg_adj_fantasy('2023-24',player))#25 seconds
    # print(pg_adj_fantasy('2022-23',player,True))
    # print(get_player_nba_team(player))
    # print(get_players_new_stats(player))
    # print(update_players_db())
    # print(search_player_in_leagues(player))
    # print(fantasy_points(find_current_year(),player))#25 seconds
    # print(specific_categories(find_current_year(),player,['AST','REB','PTS','TOV']))
    # print(specific_categories_points(find_current_year(), player, ['AST', 'REB', 'PTS', 'TOV']))
    # print(get_best_player_overall_in_categories(find_current_year(),'Util',['FGM','FGA','FTM','FTA','FG3M','PTS','AST', 'REB', 'STL','BLK', 'TOV']))
    print('a')
    
    
if __name__ == '__main__':
    URI_FANTAZY_ID_2024 = '41083'

    # test_team()
    
    # test_league()
    
    # test_stuff_todo_organize() 
    
    # Initial Configurations
    import yahoo_fantasy_api as yfa
    from yahoo_oauth import OAuth2
    from nba_api.stats.static import players
    import pandas as pd
    from nba_api.stats.endpoints import playercareerstats



    # sc = OAuth2(None, None, from_file='./pythonProject2/oauth22.json')
    # yahoo_game = yfa.Game(sc, 'nba')
    
    #Test League
    URI_FANTAZY_ID_2024 = '41083'
    NBA_SPORT_CODE = '428'
    # league_yahoo = yahoo_game.to_league(f"{NBA_SPORT_CODE}.l.{URI_FANTAZY_ID_2024}")
    
    # Specific Team
    # team_key = yahoo_fantazy_league.get_team_key_by_name('king douchebag')
    # team_roster = yahoo_fantazy_league.get_team_roster(team_key)




    # TODO - Data Plan
    # 1. Sync League Details and Settings (How many teams? How many weeks? Playoff structure)
    # ################   DONE   ##################
    
    # league_settings_df = pd.DataFrame([league_yahoo.settings()])
    # league_settings_df.to_csv("league_settings.csv", index=True)
    
    # 2. Sync all Teams with Roster
    # ################   DONE   ##################

    # league_yahoo.teams().values
    # team_rosters = {team_data['name']: league_yahoo.to_team(team_data['team_key']).roster() for team_data in league_yahoo.teams().values()}
    # team_rosters_formatted = [{"Team": team, **player} for team, roster in team_rosters.items() for player in roster]
    # pd.DataFrame(team_rosters_formatted).to_csv("team_rosters.csv", index=False)
    
    # 4. Sync Players Stat
    player_data = players.get_active_players()
    data = []

    # Loop through all players and fetch stats safely
    for i, player in enumerate(player_data):
        if i<92:
            continue
        try:
            print(f"[{i+1}/{len(player_data)}] Fetching {player['full_name']}")
            stats_obj = playercareerstats.PlayerCareerStats(player_id=player["id"], timeout=10)
            stats = {
                'name': player['full_name'],
                'stats_legend': stats_obj.season_totals_regular_season.data['headers'],
                'full_stats_according_to_legend': [only_stats for only_stats in stats_obj.season_totals_regular_season.data['data']]
                }
            data.append(stats)
        except requests.exceptions.ReadTimeout as ex:
            print(f"Timeout for player {player['full_name']}: {ex}")
            # time.sleep(5)

        except Exception as e:
            print(f"Error with player {player['full_name']}: {e}")
        
    pd.DataFrame(data).to_csv("players_stats2.csv", index=False)
   

    print("✅ Finished fetching all stats.")
    
    # 3. Sync Schedule, Matchups, Playoff Starts 
    # 5. Sync Games Scoreboard
    
    # TODO - Test Plan
    # 1. League rules
    # 2. All Players in which Teams and FA players
    # 3. (Bonus) Best players in Teams
    # 4. Matchup Schedule and Playoff schedule
    # 5. If Matchup have happened, Check Table, Matchup scoreboard, (bonus) what could be done better.
    # 6. Estimation about Matchup Scores in the future.
    # 7. General questions on team improvement.
    # 8. Estimation on best teams in the league and ranking each category
    

    
    
