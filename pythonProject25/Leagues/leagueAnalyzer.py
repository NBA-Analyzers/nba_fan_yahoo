
from Leagues.leagueAccessor import *
from  YahooLeague import YahooLeague
from DataBase import DataBase as db
def league_ranking(season_stats, league: League):
    df = league_stats(season_stats, league)
    ranked_df = league_stats(season_stats, league)
    for i in ranked_df.columns:
        if i != 'league_id' and i != 'team_key' and i != 'team_name':
            if i != 'current_TOV' and i != 'last_TOV':
                ranked_df[i] = ranked_df[i].rank(ascending=False, ).astype(int)
            else:
                ranked_df[i] = ranked_df[i].rank(ascending=True, ).astype(int)
    return ranked_df, df


def analyze_matchup(league: League):
    yl = YahooLeague(league.league_id)
    df = pd.DataFrame(yl.lg.matchups())
    bn = pd.DataFrame(df.fantasy_content.values.tolist()[1])['scoreboard']
    df_matchup = pd.DataFrame(columns=db.STATS_FOR_MATCHUP.split(','))
    count_row = 0
    count_col = 0
    try:
        for i in bn[1]['0']['matchups'].values():

            for j in (i['matchup']['0']['teams']).values():
                try:
                    df_matchup.loc[count_row] = [None] * len(df_matchup.columns)

                    team_name = j['team'][0][2]['name']
                    df_matchup.iat[count_row, count_col] = team_name
                    for k in (j['team'][1]['team_stats']['stats']):
                        count_col += 1
                        df_matchup.iat[count_row, count_col] = k['stat']['value']

                    count_row += 1
                    count_col = 0
                except TypeError:

                    continue

    except TypeError:
        pass
    # Call the recursive function with the JSON data
    return df_matchup