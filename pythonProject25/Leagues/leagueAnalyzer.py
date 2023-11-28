
from Leagues.leagueAccessor import *


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
