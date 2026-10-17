# Player projections: backtest results

How good is the player pool as a prediction? `appl/draft/backtest.py` builds the pool the way
the app does (from the seasons before a target season) and compares its ranking with how that
season actually went, using the real `DraftRanker`.

Run it from `src/`:

    python -m appl.draft.backtest 2025-26 2024-25

Season downloads are cached in the system temp folder (`nba_backtest_cache`), so repeat runs
are fast. Add a model to `MODELS` in `backtest.py` to compare it with the baseline.

Metrics (players who played at least 30 games in the target season):

- **spearman**: rank correlation between projected and actual value (1 = same order).
- **top-N overlap**: share of the actual top 150 that the projection also puts in its top 150.
- **missing**: actual top-150 players the pool had no row for.

## Baseline (the pool as built before the projection work)

Last two seasons, weights 0.7 / 0.3, each scaled by games played.

| Target season | spearman | top-150 overlap | missing from top 150 |
|---|---|---|---|
| 2025-26 | 0.736 | 70.7% | 8 |
| 2024-25 | 0.834 | 78.7% | 7 |

Players the baseline could not project:

- 2025-26: Cooper Flagg, VJ Edgecombe, Kon Knueppel, Derik Queen, Ryan Kalkbrenner,
  Dylan Cardwell, Maxime Raynaud, Cedric Coward (all rookies).
- 2024-25: Ja Morant, Ty Jerome, Kel'el Ware, Zach Edey, Lonzo Ball, Guerschon Yabusele,
  Donovan Clingan (rookies, plus players who missed most of the season before).

The new model has to beat these numbers to replace the baseline.

## Players with no history (rookies, a lost season)

Two changes, now live in `draft/player_pool.py`:

1. **Games played blend across seasons.** The durability factor used to be last season's games
   alone, so a star hurt last season (Ja Morant, 9 games) fell under the ranker's 15-game cutoff.
   Games now blend with the season weights from the newest season back to the player's debut
   (a missed season counts as 0, seasons before his debut don't count), and never drop below
   last season's games.
2. **ESPN projections fill the gaps.** The ingest job also fetches ESPN fantasy's preseason
   projections (`EspnSource.projections`) and adds a row, marked `"projected": true`, for every
   projected player the history has no row for. Rows the history covers are never replaced.
   Once the season starts, `blend_current` blends a rookie's real games with his projection
   instead of trusting his first few games raw. If ESPN is down, the pool is built without them.

The backtest uses ESPN's real preseason projections for each past season (ESPN still serves them),
so the `projections` model doesn't see the outcome. The `baseline` model includes the games change:

| Target season | model | spearman | top-150 overlap | missing from top 150 |
|---|---|---|---|---|
| 2025-26 | baseline | 0.729 | 70.7% | 8 |
| 2025-26 | projections | 0.723 | 71.3% | 4 |
| 2024-25 | baseline | 0.834 | 78.0% | 6 |
| 2024-25 | projections | 0.819 | 78.7% | 2 |

Spearman dips because the projections model is scored on more players: it now includes the
rookies, who are the hardest to project. Top-150 overlap goes up and the missing count halves.

Still missing: late picks and undrafted rookies ESPN didn't project (Ryan Kalkbrenner, Dylan
Cardwell, Maxime Raynaud, Cedric Coward), and Ty Jerome and Lonzo Ball (no projection and
almost no games in the last two seasons). Once the season starts these players enter the
in-season pool from their real games.

## Per-case weights and projected games (the pool today)

The pool now trusts three sources in this order: **last season > ESPN's projection for the
coming season > the season before**. A season only feeds the per-game stats when the player
played at least 30 games in it (`MIN_SAMPLE_GAMES`), and the weights depend on which seasons
pass (`CASE_WEIGHTS` in `draft/player_pool.py`):

| Case (`basis`) | Last season | Projection | Season before |
|---|---|---|---|
| Both seasons have 30+ games (`two_seasons`) | 50% | 35% | 15% |
| Only last season does (`last_season`) | 60% | 40% | - |
| Only the season before does (`prior_season`, hurt or away last year) | - | 65% | 35% |
| Neither does (`projection`, rookies and small samples) | - | 100% | - |

With no ESPN projection, the remaining weights are rescaled. A player under 30 games in both
seasons and with no projection is pooled across the two if they add up to 30+ games
(`pooled`). Otherwise he is left out.

**Projected games.** `GP` is now the number of games a player is expected to play: last season
50%, ESPN's projected games 35%, the season before 15%. Every season counts here, even a short
one. A season missed after his debut counts as 0. The ranker scales a player's value by
`(GP / 82) ** 0.5` (`HEALTH_EXPONENT`), so 60 games keeps about 86% of the value and 41 games
about 71%. Auction prices use the same factor. The factor only ever lowers a positive value,
so missing games never makes a below-average player look better.

Backtest (`baseline` is the old 0.7 / 0.3 history blend). `games MAE` is the average miss on
games played:

| Target season | model | spearman | top-150 overlap | missing | games MAE |
|---|---|---|---|---|---|
| 2025-26 | baseline | 0.729 | 70.7% | 8 | 14.5 |
| 2025-26 | per-case (`projections`) | 0.743 | 70.7% | 5 | 13.4 |
| 2024-25 | baseline | 0.834 | 78.0% | 6 | 14.5 |
| 2024-25 | per-case (`projections`) | 0.837 | 79.3% | 3 | 12.4 |

The new pool beats the old projections model (0.723 / 0.819 spearman) as well. Cam Spencer
(2025-26) and Justin Champagnie (2024-25) now drop out before the season: under 30 games in
both seasons combined and no ESPN projection. They enter the in-season pool once they play.
