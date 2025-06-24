

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
    import pandas as pd
    from nba_api.stats.endpoints import playercareerstats
    import json 


    sc = OAuth2(None, None, from_file='./pythonProject2/oauth22.json')
    yahoo_game = yfa.Game(sc, 'nba')
    
    #Test League
    URI_FANTAZY_ID_2024 = '41083'
    NBA_SPORT_CODE = '428'
    league_yahoo = yahoo_game.to_league(f"{NBA_SPORT_CODE}.l.{URI_FANTAZY_ID_2024}")
    
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
    
    # 3. Sync Players Stat (TODO)
    # player_data = players.get_active_players()
    # data = []
    # # failed_players_data = ['DeMar DeRozan', 'David Duke Jr.', 'Kris Dunn', 'Ryan Dunn', 'Kevin Durant', 'Jalen Duren', 'Tari Eason', 'Zach Edey', 'Anthony Edwards', 'Jesse Edwards', 'Justin Edwards', 'Kessler Edwards', 'Keon Ellis', 'Joel Embiid', 'Tyson Etienne', 'Drew Eubanks', 'Tosan Evbuomwan', 'Danté Exum', 'Bruno Fernando', 'Kyle Filipowski', 'Dorian Finney-Smith', 'Adam Flagler', 'Trentyn Flowers', 'Malachi Flynn', 'Simone Fontecchio', "De'Aaron Fox", 'Enrique Freeman', 'Markelle Fultz', 'Johnny Furphy', 'Daniel Gafford', 'Darius Garland', 'Marcus Garrett', 'Luka Garza', 'Keyonte George', 'Kyshawn George', 'Paul George', 'Taj Gibson', 'Josh Giddey', 'Shai Gilgeous-Alexander', 'Anthony Gill', 'Collin Gillespie', 'Rudy Gobert', 'Jordan Goodwin', 'Aaron Gordon', 'Eric Gordon', 'Jazian Gortman', 'Jerami Grant', 'AJ Green', 'Draymond Green', 'Jalen Green', 'Javonte Green', 'Jeff Green', 'Josh Green', 'Quentin Grimes', 'Mouhamed Gueye', 'Rui Hachimura', 'Tyrese Haliburton', 'PJ Hall', 'Tim Hardaway Jr.', 'James Harden', 'Jaden Hardy', 'Jett Howard', 'Kevin Huerter', 'Keshad Johnson', 'Nikola Jokić', 'Colby Jones', 'Dillon Jones', 'Herbert Jones', 'Isaac Jones', 'Kai Jones', 'Mason Jones', 'Spencer Jones', 'Tre Jones', 'Tyus Jones', 'Derrick Jones Jr.', 'DeAndre Jordan', 'Cory Joseph', 'Nikola Jović', 'Johnny Juzang', 'Yuki Kawamura', 'Kylor Kelley', 'Luke Kennard', 'Walker Kessler', 'Braxton Key', 'Corey Kispert', 'Maxi Kleber', 'Bobi Klintman', 'Dalton Knecht', 'Kevin Knox II', 'Tyler Kolek', 'Christian Koloko', 'John Konchar', 'Luke Kornet', 'Vít Krejčí', 'Jonathan Kuminga', 'Kyle Kuzma', 'Jake LaRavia', 'Zach LaVine', 'Skal Labissiere', 'Jock Landale', 'Pelle Larsson', 'A.J. Lawson', 'Caris LeVert', 'Damion Lee', 'Alex Len', 'Kawhi Leonard', 'Malevy Leons', 'Maxwell Lewis', 'E.J. Liddell', 'Damian Lillard', 'Dereck Lively II', 'Chris Livingston', 'Kevon Looney', 'Brook Lopez', 'Kevin Love', 'Kyle Lowry', 'Seth Lundy', 'Trey Lyles', 'Sandro Mamukelashvili', 'Terance Mann', 'Jalen McDaniels', 'Doug McDermott', 'Monté Morris', 'Trey Murphy III', 'Dejounte Murray', 'Jamal Murray', 'Keegan Murray', 'Kris Murray', 'Svi Mykhailiuk', 'Pete Nance', 'Larry Nance Jr.', 'Andrew Nembhard', 'Aaron Nesmith', 'Tristen Newton', 'Georges Niang', 'Daishen Nix', 'Zeke Nnaji', 'Miles Norris', 'Jaylen Nowell', 'Jusuf Nurkić', "Royce O'Neale", 'Jahlil Okafor', 'Chuma Okeke', 'Josh Okogie', 'Onyeka Okongwu', 'Isaac Okoro', 'Quincy Olivari', 'Kelly Olynyk', 'Kelly Oubre Jr.', 'Chris Paul', 'Cameron Payne', 'Elfrid Payton', 'Gary Payton II', 'Drew Peterson', 'Julian Phillips', 'Jalen Pickett', 'Scotty Pippen Jr.', 'Daeqwon Plowden', 'Mason Plumlee', 'Brandin Podziemski', 'Jakob Poeltl', 'Jordan Poole', 'Craig Porter Jr.', 'Kevin Porter Jr.', 'Michael Porter Jr.', 'Bobby Portis', 'Kristaps Porziņģis', 'Quinten Post', 'Micah Potter', 'Dwight Powell', 'Norman Powell', 'Taurean Prince', 'Payton Pritchard', 'Olivier-Maxence Prosper', 'Zyon Pullin', 'Trevelin Queen', 'Neemias Queta', 'Immanuel Quickley', 'Lester Quinones', 'Terry Rozier', 'Rayan Rupert', 'Dru Smith', 'Jalen Smith', 'Tolu Smith', 'Tyler Smith', 'Jabari Smith Jr.', 'Nick Smith Jr.', 'Jeremy Sochan', 'Cam Spencer', 'Pat Spencer', 'Jaden Springer', 'Isaiah Stevens', 'Lamar Stevens', 'Isaiah Stewart', 'Julian Strawther', 'Max Strus', 'Jalen Suggs', 'Cole Swider', "Jae'Sean Tate", 'Jayson Tatum', 'Terry Taylor', 'Garrett Temple', 'Dalen Terry', 'Daniel Theis', 'Cam Thomas', 'Amen Thompson', 'Ausar Thompson', 'Ethan Thompson', 'Klay Thompson', 'Tristan Thompson', 'JT Thor', 'Matisse Thybulle', 'Xavier Tillman', 'Drew Timme', "Nae'Qwan Tomlin", 'Nikola Topić', 'Jacob Toppin', 'Obi Toppin', 'Karl-Anthony Towns', 'Armel Traoré', 'Luke Travers', 'Gary Trent Jr.', 'Oscar Tshiebwe', 'P.J. Tucker', 'Myles Turner', 'Hunter Tyson', 'Jaylon Tyson', 'Stanley Umude', 'Jonas Valančiūnas', 'Fred VanVleet', 'Jarred Vanderbilt', 'Devin Vassell', 'Gabe Vincent', 'Tristan Vukcevic', 'Nikola Vučević', 'Dean Wade', 'Franz Wagner', 'Moritz Wagner', 'Derrick White', 'Dariq Whitehead', 'Tristan da Silva', 'Vlatko Čančar', 'Dario Šarić']
    # # print(len(failed_players_data))
    # failed_players = []

    # # Loop through all players and fetch stats safely
    # for i, player in enumerate(player_data):
    #     try:
    #         print(f"[{i+1}/{len(player_data)}] Fetching {player['full_name']}")
    #         stats_obj = playercareerstats.PlayerCareerStats(player_id=player["id"], timeout=10)
    #         stats = {
    #             'name': player['full_name'],
    #             'stats_legend': stats_obj.season_totals_regular_season.data['headers'],
    #             'full_stats_according_to_legend': [only_stats for only_stats in stats_obj.season_totals_regular_season.data['data']]
    #             }
    #         data.append(stats)
    #     except requests.exceptions.ReadTimeout as ex:
    #         failed_players.append((player['full_name'], player["id"]))
    #         print(f"Timeout for player {player['full_name']}: {ex}")
    #         time.sleep(30)

    #     except Exception as e:
    #         failed_players.append((player['full_name'], player["id"]))
    #         print(f"Error with player {player['full_name']}: {e}")
        
    # pd.DataFrame(data).to_csv("players_stats3.csv", index=False)

    # print("✅ Finished fetching all stats.")
    # print(f"Failed players: {failed_players}")
   

    # 4. Sync Schedule, Matchups
    # # Collect all matchups
    # matchup_data = []
    
    # for week in range(start_week, end_week + 1):
    #     matchups = league_yahoo.matchups(week)
    #     week_matchups = matchups['fantasy_content']['league'][1]['scoreboard']['0']
    #     matchup = extract_matchup_info(week_matchups['matchups'])
    #     matchup_data.append(matchup)


    # # Convert to JSON
    # matchup_data_json = json.dumps(matchup_data, indent=2)
    # with open("league_matchups.json", "w") as f:
    #     f.write(matchup_data_json)

    # 5. Sync Games Scoreboard, Standings
    # 6. Sync FA players
    
    # TODO - Test Plan
    # 1. League rules
    # 2. All Players in which Teams and FA players
    # 3. (Bonus) Best players in Teams
    # 4. Matchup Schedule and Playoff schedule
    # 5. If Matchup have happened, Check Table, Matchup scoreboard, (bonus) what could be done better.
    # 6. Estimation about Matchup Scores in the future.
    # 7. General questions on team improvement.
    # 8. Estimation on best teams in the league and ranking each category
    # 9. How to know which players played in each matchup.
    # 10. Check if he knows that the team is going to play a bad team so the stat inflates. 
    

