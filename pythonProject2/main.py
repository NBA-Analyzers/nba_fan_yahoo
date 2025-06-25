# from Leagues.leagueAccessor import LeagueAccessor
#from Leagues.league import League
# from Leagues.leagueAnalyzer import analyze_matchup

#from YahooLeague import YahooLeague




#import time

#import requests

#from Teams.team import Team
#from Teams.teamAnalyzer import get_matchup_of_team

def test_team():
    ### class Team
    #team = Team('428.l.144401.t.1', 'Uri\'s Game-Changing Team', 'IFSL - Robinson League', '428.l.144401')
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
    league = League('428.l.144401', 'Test League')
    print(f"Successfully created League object with ID: {league.league_id}")
    print(f"draft results: {league.draft_results()}")
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
    #print('a')
    
def test_stuff_todo_organize():
    update_players_db()
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


def test_yahoo_league():
    uri = YahooLeague('428.l.41083')
    print(uri.league_id)
    print(uri.league_name())
    print(uri.league_teams_id())
    print(uri.get_teamkey('king douchebag'))
    print(uri.get_matchup(3))
        
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

from multiprocessing.spawn import import_main_path
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

STAT_ID_TO_NAME = {
    "5": "Field Goal Percentage (FG%)",
    "8": "Free Throw Percentage (FT%)",
    "10": "3-Point Field Goals Made (3PTM)",
    "12": "Points",
    "15": "Rebounds",
    "16": "Assists",
    "17": "Steals",
    "18": "Blocks",
    "19": "Turnovers",
    "9004003": "Field Goals Made/Attempted (FGM/FGA)",
    "9007006": "Free Throws Made/Attempted (FTM/FTA)"
}  
# Extract key fantasy matchup data
def extract_matchup_info(parsed):
    matchups = []

    for key, matchup_wrap in parsed.items():
        if key == "count":
            continue
        matchup = matchup_wrap.get("matchup", {})
        week = matchup.get("week")
        team_data = []

        for team_index in ["0", "1"]:
            team_info = matchup.get("0", {}).get("teams", {}).get(team_index, {}).get("team", [])
            if not team_info:
                continue

            metadata = team_info[0]
            stats = team_info[1].get("team_stats", {}).get("stats", [])
            team_points = team_info[1].get("team_points", {}).get("total", None)

            team = {
                "week": week,
                "team_name": next((d.get("name") for d in metadata if "name" in d), None),
                "team_key": next((d.get("team_key") for d in metadata if "team_key" in d), None),
                "score": team_points,
                "stats": {STAT_ID_TO_NAME[s["stat"]["stat_id"]]: s["stat"]["value"] for s in stats}
            }
            team_data.append(team)
        
        team_0_score = team_data[0]['score']
        team_1_score = team_data[1]['score']
        if team_0_score > team_1_score:
            team_win_name = team_data[0]['team_name']
            team_win_score = team_data[0]['score']
        elif team_1_score>team_0_score:
            team_win_name = team_data[0]['team_name']
            team_win_score = team_data[0]['score']
        else: 
            team_win_name = "Finshed In a Draw"
            team_win_score = team_data[0]['score']
            
        stat_winners =0
        if len(team_data) == 2:
            matchups.append({
                "week": week,
                "team_1": team_data[0],
                "team_2": team_data[1],
                "team_win_name": team_win_name,
                "team_win_score": team_win_score
            })

    return matchups   
    
if __name__ == '__main__':
    URI_FANTAZY_ID_2024 = '41083'

    # test_team()
    
    # test_league()
    
    # test_stuff_todo_organize() 
    
    # Initial Configurations
    import yahoo_fantasy_api as yfa
    from yahoo_oauth import OAuth2
    from nba_api.stats.static import players
    
    from nba_api.stats.endpoints import playercareerstats
    import json 
    from collections import defaultdict

# Your existing setup

from dailyRoster import print_players_for_day, print_players_entire_season, print_all_teams_custom_range, export_to_csv_pivot, export_to_json_pivot,export_to_json_simple
from boxScore import collect_and_export_nba_boxscores

if __name__ == '__main__':
    URI_FANTAZY_ID_2024 = '41083'
    week = 21
    sc = OAuth2(None, None, from_file='pythonProject2/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    lg = yahoo_game.to_league('428.l.41083')
    # print("=== NBA Box Scores Collector ===")
    
    # # Test with a more recent date that likely has games
    # print("Testing with different dates...")
    
    # # Option 1: Try a few different dates
    # test_dates = ["2024-02-14", "2024-03-15"]
    
    # for test_date in test_dates:
    #     print(f"\n--- Testing {test_date} ---")
    #     try:
    #         filename = collect_and_export_nba_boxscores(test_date)
    #         if filename:
    #             print(f"✅ Success with {test_date}")
    #             break
    #         else:
    #             print(f"❌ No data for {test_date}")
    #     except Exception as e:
    #         print(f"❌ Error with {test_date}: {e}")
    #         continue

    # # 2. Get and print the league standings
    # print("--- League Standings ---")
    # standings = lg.standings()
    # for team in standings:
    #     outcomes = team['outcome_totals']
    #     print(f"Rank: {team['rank']}, Team: {team['name']}, Record: {outcomes['wins']}-{outcomes['losses']}-{outcomes['ties']}")
    # print("") # Add a newline for spacing

    # # 3. Get and print the list of teams
    # print("--- All Teams in League ---")
    # teams = lg.teams()
    # for team_key, team_data in teams.items():
    #     print(f"- {team_data['name']}")

    # # test_stuff_todo_organize() 
    
    # # 4. Sync Players Stat
    # # player_data = players.get_active_players()
    # # data = []
    
    # # Check if we have a partial save to resume from
    # # try:
    # #     partial_df = pd.read_csv("players_stats2_partial.csv")
    # #     data = partial_df.to_dict('records')
    # #     start_index = len(data) + 92  # Resume from where we left off
    # #     print(f"📂 Resuming from player {start_index} (found {len(data)} players already processed)")
    # # except FileNotFoundError:
    # #     start_index = 92
    # #     print("🆕 Starting fresh player data collection")

    # # Loop through all players and fetch stats safely
    # # for i, player in enumerate(player_data):
    # #     if i < start_index:
    # #         continue
        
    # #     max_retries = 3
    # #     retry_count = 0
        
    # #     while retry_count < max_retries:
    # #         try:
    # #             print(f"[{i+1}/{len(player_data)}] Fetching {player['full_name']}")
                
    # #             # Add delay between requests to avoid rate limiting
    # #             if i > 92:  # Skip delay for first request
    # #                 time.sleep(1.5)  # 1.5 second delay between requests
                
    # #             # Increase timeout and add retry logic
    # #             stats_obj = playercareerstats.PlayerCareerStats(
    # #                 player_id=player["id"], 
    # #                 timeout=30  # Increased timeout from 10 to 30 seconds
    # #             )
                
    # #             stats = {
    # #                 'name': player['full_name'],
    # #                 'stats_legend': stats_obj.season_totals_regular_season.data['headers'],
    # #                 'full_stats_according_to_legend': [only_stats for only_stats in stats_obj.season_totals_regular_season.data['data']]
    # #             }
    # #             data.append(stats)
    # #             break  # Success, exit retry loop
                
    # #         except requests.exceptions.ReadTimeout as ex:
    # #             retry_count += 1
    # #             print(f"Timeout for player {player['full_name']} (attempt {retry_count}/{max_retries}): {ex}")
    # #             if retry_count < max_retries:
    # #                 print(f"Retrying in {retry_count * 2} seconds...")
    # #                 time.sleep(retry_count * 2)  # Exponential backoff
    # #             else:
    # #                 print(f"Failed to fetch {player['full_name']} after {max_retries} attempts")
                    
    # #         except requests.exceptions.ConnectionError as ex:
    # #             retry_count += 1
    # #             print(f"Connection error for player {player['full_name']} (attempt {retry_count}/{max_retries}): {ex}")
    # #             if retry_count < max_retries:
    # #                 print(f"Retrying in {retry_count * 3} seconds...")
    # #                 time.sleep(retry_count * 3)  # Longer delay for connection errors
    # #             else:
    # #                 print(f"Failed to fetch {player['full_name']} after {max_retries} attempts")
                    
    # #         except Exception as e:
    # #             print(f"Unexpected error with player {player['full_name']}: {e}")
    # #             break  # Don't retry for unexpected errors
        
    # #     # Save progress every 50 players to avoid losing data
    # #     if (i + 1) % 50 == 0:
    # #         print(f"💾 Saving progress... ({i + 1} players processed)")
    # #         pd.DataFrame(data).to_csv("players_stats2_partial.csv", index=False)
    
    # # # Save final results
    # # pd.DataFrame(data).to_csv("players_stats2.csv", index=False)
   
    # # print("✅ Finished fetching all stats.")
    
    
    # # 5. Get daily roser for each team 
    # #custom_data = print_all_teams_custom_range(lg, "2023-10-24", "2024-03-24")
    # #pivot_file = export_to_json_simple(custom_data, "my_pivot")
    
    
    
    # # 6. Sync Schedule, Matchups
    # # Collect all matchups
    # # matchup_data = []
    
    # # for week in range(start_week, end_week + 1):
    # #     matchups = league_yahoo.matchups(week)
    # #     week_matchups = matchups['fantasy_content']['league'][1]['scoreboard']['0']
    # #     matchup = extract_matchup_info(week_matchups['matchups'])
    # #     matchup_data.append(matchup)


    # # # Convert to JSON
    # # matchup_data_json = json.dumps(matchup_data, indent=2)
    # # with open("league_matchups.json", "w") as f:
    # #     f.write(matchup_data_json)

    # # 6. Sync Games Scoreboard, Standings
    
    # # 7. Sync FA players
    
    # free_agents = lg.free_agents('Util')
    # free_agents_json = json.dumps(free_agents, indent=2)
    # with open("free_agents.json", "w") as f:
    #     f.write(free_agents_json)

 
    
    
    
    # # TODO - Test Plan
    # # 1. League rules
    # # 2. All Players in which Teams and FA players
    # # 3. (Bonus) Best players in Teams
    # # 4. Matchup Schedule and Playoff schedule
    # # 5. If Matchup have happened, Check Table, Matchup scoreboard, (bonus) what could be done better.
    # # 6. Estimation about Matchup Scores in the future.
    # # 7. General questions on team improvement.
    # # 8. Estimation on best teams in the league and ranking each category
    # # 9. How to know which players played in each matchup.
    # # 10. Check if he knows that the team is going to play a bad team so the stat inflates. 
    

