# Draft Night Assistant — Build Summary

2026-10-06

## Overview

The draft assistant is built and compiles, but it has not run end-to-end: stats.nba.com was unreachable from the dev machine, so the player pool is not generated yet and nothing was tried against a real Yahoo league. It lets a manager set a punt strategy, then follows a live Yahoo draft and recommends the best available player for that build and the current roster.

Decisions made with the user:

- **Interface:** a live draft page that polls Yahoo, not a chat feature.
- **Punts:** the manager ticks categories to punt; the assistant also suggests punts from the roster so far.
- **Ranking:** 9-category z-scores with punted categories removed, plus a boost for categories the roster is weak in.
- **Stats:** 2025-26 weighted 70% and 2024-25 weighted 30%, because the draft is before the 2026-27 season.
- **Yahoo data:** preseason rank and ADP shown as context, not blended into the score.
- **Scope:** snake turn tracking, auction bid values, mock mode and a dashboard link.

## How it works on draft night

The manager opens **Draft Assistant** from the new button next to "AI Chat" on each league card, and the page refreshes from Yahoo every 10 seconds.

| Feature | What the manager sees |
| --- | --- |
| Punts | Category chips to tick. After 3 or more picks, the two weakest roster categories are suggested, one click to punt. |
| Recommendations | Top 25 available players, with a colored z-score per category (punted ones struck out), strengths and weaknesses. |
| Snake drafts | "You pick in N picks (pick #X)", or "You're on the clock!". |
| Auction drafts | Your remaining budget and a suggested bid per player, scaled to the money left league-wide. |
| Yahoo context | Yahoo preseason rank and ADP, with a "value" badge when our rank is at least 15 spots ahead of ADP. |
| Roster panel | Category strength bars for the players drafted so far, and a feed of the last 12 picks. |
| Mock mode | A toggle to mark players "Taken" or "Mine" by hand, to practice with no Yahoo draft. Stored in the browser only. |

## Architecture

The draft page calls a new Flask blueprint, which gets live picks from a Yahoo tracker and recommendations from a z-score ranker built on a cached player pool.

| File | Role |
| --- | --- |
| `src/appl/draft/player_pool.py` | Blends 2025-26 and 2024-25 per-game stats from nba_api, caches to `data/draft/player_pool_2026-27.json`, normalizes names |
| `src/appl/draft/ranker.py` | Z-scores, punts, roster need weights, suggested punts, auction values |
| `src/appl/draft/jev_chooser.py` | The Jev layer: builds the request from the shortlist, calls Jev, applies the confidence rule, falls back to the ranker |
| `src/appl/draft/mock_eval.py` | Mock snake drafts against bots, to compare baseline, ranker and Jev strategies |
| `src/appl/draft/yahoo_draft.py` | Live picks, my roster, snake turn math, auction budgets, Yahoo rank and ADP |
| `src/appl/router/draft_routes.py` | `/draft/<league_id>` page and `/draft/<league_id>/state` (GET live, POST mock) |
| `src/appl/static/draft.html` | The draft-night page |
| `src/appl/tests/unit/test_draft.py`, `test_draft_routes.py` | 38 tests: ranker, matching, snake math, Jev modes and fallback, simulator, Flask routes |
| `src/appl/router/__init__.py`, `main_routes.py` | Existing files edited: register the blueprint, add the dashboard button |

Also added on 2026-10-07: fuzzy name matching in the ranker (similarity 0.88) and a manual draft-slot box for snake drafts when Yahoo does not expose the slot.

**How players are scored**

1. Each category is z-scored against all players with 15 or more games. The top teams × roster-size players become the draftable pool, and everyone is re-scored against that pool.
2. FG% and FT% are volume-weighted: impact = makes − league % × attempts. Turnovers are inverted.
3. Score = sum of z over non-punted categories × a need weight (0.5 to 1.5, active once 3 players are drafted) × an availability factor (0.85 to 1.0, by games played).
4. Auction bids give every spot $1 and split the rest by value above the last draftable player, scaled to the money left league-wide.

## Jev as the final chooser

Jev, TypeSafe AI's decision model, picks the player from a shortlist the engine builds; the engine stays the baseline and the fallback. Built on 2026-10-07 in `draft/jev_chooser.py` and tested with fake clients. The live call works with the new key (checked 2026-10-08: 390 picks, no fallbacks).

1. **Shortlist.** The engine ranks the available players and keeps the top 25. Jev's Choice question accepts up to 255 options.
2. **Strategy.** The manager sets punts and optional free text ("I need a big who blocks shots"). In AI mode, an LLM turns that text into punts and category weights.
3. **Question to Jev.** The state holds the roster, punts, category needs and the shortlist. Each player's z-scores are precomputed and sent as labeled values ("REB +1.8"), because Jev cannot do arithmetic.
4. **Answer.** Jev returns the pick, a probability for each option and a confidence value.
5. **Confidence rule.** Above a threshold, the pick is highlighted or auto-selected. Below it, the manager sees the top 3 and chooses. If Jev fails or times out, the engine's top pick is used.
6. **Explanation.** An LLM writes one sentence on why the player fits, since Jev cannot write prose.

Three modes: **Manual** (engine ranking only), **Assist** (Jev recommends, the manager decides) and **Auto** (Jev decides when confident).

| Open question | Why it matters |
| --- | --- |
| How to call Jev from Python | The documented route is the Vercel AI SDK `evaluate` call through the AI Gateway, which is JavaScript. Resolved: a Python SDK and an HTTP API exist (see below). |
| Price after the free promotion | $0.042 per million input tokens, output free. One source reports TypeSafe paused new signups on September 22, 2026; Vercel AI Gateway is the fallback. Verify current access before building. |
| Does Jev beat the engine? | No public benchmarks exist. Run both in mock drafts and keep Jev only if it does better. |
| Confidence threshold | Must be calibrated on mock drafts before Auto mode is trusted. |
| Data sent to a third party | Roster and shortlist stats leave the app; no league credentials should be included. |

**Real-data results (2026-10-08).** 687 players from ESPN, 30 mock drafts per punt choice, seat 5 of 12 against bot teams. Share of all 9 categories won:

| Punt choice | Plain best-available | Ranker | Jev (shortlist 8) |
| --- | --- | --- | --- |
| FT% | 57.5% | 60.0% | 58.6% |
| FT% + AST | 57.5% | 53.2% | 54.3% |

Punting FT% alone beats plain drafting by 2.5 points (±0.9), but punting FT% and AST loses by 4.3 (±0.8), so in this simulation single punts pay off and double punts do not. After the ranker's need weight was tuned from 0.25 to 0.5, Jev no longer adds a clear gain: it is 1.4 points behind the ranker on FT% (±0.6) and 1.1 ahead on FT% + AST (±0.6, not significant). Its earlier 6-point edge came from the untuned ranker. Jev reached 0.6 confidence on only 14% to 22% of picks.

Recommendation: keep Manual as the default, keep Assist as an optional second opinion, and do not use Auto. These are simulation results against bots that draft by consensus rank, not a forecast for your league.

**Integration check (2026-10-07).** Jev can be called from Flask with the `typesafe-sdk` Python package, or with `POST https://api.typesafe.ai/v1/systemone` and a Bearer key, using model `jev-latest`. Vercel's AI Gateway also offers an HTTP `/v1/evaluate` route. A Choice question returns the pick, a confidence value and a probability per option. Limits: 64k tokens per request, 1,200 requests per minute, text only. The sources disagree on how options are passed (an `options` list versus a `criteria` map of option to description), and the installed SDK confirms the `criteria` form, which the build uses.

Sources: [DataNorth](https://datanorth.ai/blog/jev-what-it-is-and-why-this-new-model-matters), [mager.co](https://mager.co/blog/2026-09-19-jev-decision-model/), [Eden AI](https://www.edenai.co/post/jev-a-new-kind-of-ai-model-built-for-decisions-not-conversation).

## What was tested

The ranking and tracking logic passed on a synthetic pool of 200 players; the live pieces could not be tested.

| Check | Result |
| --- | --- |
| Players with under 15 games are excluded | Pass |
| Punting FT% | Bigs in the top 25 rose from 12 to 21 |
| Punting AST | 23 of the top 25 are bigs |
| Snake math: 12 teams, position 3, 14 picks made | Next pick is #22, as expected |
| Auction bids for 156 spots and $2,400 | Sum to $2,397 (rounding), max $48, min $1 |
| Season blending, 70/30 weighted by games played | 17.0 points for a full two-season player; one-season players use that season |
| Yahoo draft-analysis parsing on a hand-built payload | Pass |
| Python compile check and JavaScript syntax check | Pass |
| Building the player pool from stats.nba.com | **Failed**: timeouts, then dropped connections, even with retries |
| Routes against a real Yahoo league and the page in a browser | **Not run**: the Supabase config needs env vars that are not set locally |

**Update 2026-10-08:** the full suite passes (139 tests, 38 of them new). The page was checked in a browser against a fake backend: decision card, punt chips, mock mode, saved state and a 390 px phone layout all work, with no console errors. The Flask routes are tested with a fake Yahoo tracker. The player pool is built from ESPN's stats feed (687 players, 529 with enough games to rank), because stats.nba.com is blocked on this network and on the manager's PC; nba_api stays as the fallback.

## Auction mode

Added on 2026-10-08 for auction leagues, built around Yahoo's rules: a 30-second nomination clock, a 20-second bid clock, a $1 minimum, and a max bid of your budget minus $1 for every open roster spot.

- **Bid card.** Type a name (press `/` to jump to the box) or click a table row. The card shows "Bid up to $X", what the player is worth to your build, what the room will likely pay, your max bid, whether he fills an open starting spot, and how many rivals can afford him. Yahoo's API does not expose the player currently on the block, so the name has to be entered by hand.
- **Prices that follow your build.** "Worth to you" uses your punts and roster needs; "Others pay" uses generic value. Both are recalculated from the money left after every sale, so inflation is built in, and the page states it in words.
- **Your money panel.** Budget left, max bid, open roster spots, and the richest rivals with their max bids.
- **Positions (warn only).** Required slots come from Yahoo's league settings and each player's eligible positions from Yahoo. The page lists the starting spots you still need and flags a nominee who fills one.
- **Faster refresh.** Every 4 seconds in a live auction (10 seconds otherwise). Practice mode asks what each player sold for, so budgets and inflation work there too.
- **Demo.** `python -m appl.draft.demo_server`, then open http://localhost:5055/demo?auction=1.

Not checked against a real Yahoo league: Yahoo's average-cost field (the column is simply hidden if it is missing), the position lookup by player name, and whether Yahoo tolerates a 4-second refresh.

## The Draft tab

Inside a league, the Ask page and the Draft page share a tab bar (Ask | Draft) under the site header, so people can switch between asking questions and draft help without going back to My leagues. The Draft page now uses the same layout, theme and header as the rest of the site. The tab bar appears only on those two pages and only for Yahoo leagues; a manual league has no chat, so it shows the Draft page without tabs. Switching to Ask starts a new chat, as it already does from the dashboard.

## Roster spots, punt ideas and cash advice

**Roster spots by position.** A manual league takes a count for PG, SG, G, SF, PF, F, C, Util, Bench and Injured list, in the new-league form and in the league settings. The counts decide the roster size (the injured list is not drafted into), and the page lists the starting positions you still need and, in an auction, whether the nominated player fills one. Each player's position comes from ESPN's listing (Guard, Forward or Center for most, so the check is looser than Yahoo's) and it only warns. Yahoo leagues keep using Yahoo's eligibility. Leagues made before this keep a plain roster size and get no position check.

**Team names are optional.** The new-league form has an optional list of team names; without it teams are Team 1, Team 2 and so on. Names can be changed later in the league settings.

**Cash tracking (auctions).** Log each pick with the team and the price. The page keeps every team's money left, max bid and open spots, every player's price on each roster, and your own budget, and recalculates prices from the money left after each sale.

**Punt idea.** Once two players are on your team, the page suggests the one category your players are weakest in (if they average below -0.4) and shows how the best available players change if you skip it. It suggests only one, and only while you are skipping nothing, because mock drafts showed one skipped category helps but two usually hurts. The switch "Choose for me" applies the idea automatically and re-ranks the list.

**What you can do (auctions).** Plain advice from the cash: how your money per open spot compares with the league average, who has the most cash and who can hardly bid any more, a player to nominate for yourself (worth more to you than the room will pay, and few rivals can afford him), and a player to nominate to make rivals spend (the room pays a lot, he is worth little to you, and many rivals can afford him).

## Before draft night

Four things need you, plus one decision. The Jev key and the player pool are done. Nothing is committed yet.

- [ ] **See the page with no login:** from `src/`, run `python -m appl.draft.demo_server` and open http://localhost:5055/demo (add `?auction=1` for an auction league). It uses the real player pool and the real Jev with a fake Yahoo draft.
- [ ] **Try the page on your real league** before the draft: Dashboard, then Draft Assistant. Check the Yahoo rank and ADP columns, the snake countdown (type your draft slot if the box appears) and the "no stats match" warning. Practice in mock mode, and in a Yahoo mock draft if you can.
- [ ] **Add `JEV_API_KEY` to Cloud Run** through Secret Manager, like your other secrets (commands below). `typesafe-sdk` is already in `requirements.txt`.
- [ ] **Review and commit.** New files: `src/appl/draft/`, `router/draft_routes.py`, `static/draft.html`, the two test files, `docs/draft-assistant.md` and `src/appl/data/draft/player_pool_2026-27.json`. Edited: `router/__init__.py` and `requirements.txt`. To refresh the pool, run `python -m appl.draft.player_pool` from `src/` (about 10 seconds).
- [ ] **Decide whether to keep Jev.** It works and is cheap ($0.042 per million input tokens), but the simulation shows no reliable gain over the ranker. Manual is the default; Assist is an optional second opinion.

### Adding the Jev key on Cloud Run

The service is `fantasy-ai` in `europe-west1` (project `nbafantasy-511015`), and it runs as `fantasy-app`. From the repo root, in Git Bash. The key must have no trailing newline, or TypeSafe rejects it:

```
grep '^JEV_API_KEY=' src/.env | cut -d= -f2- | tr -d '

"' | gcloud secrets create jev-api-key --data-file=-
gcloud secrets add-iam-policy-binding jev-api-key --member=serviceAccount:fantasy-app@nbafantasy-511015.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

Then add `--update-secrets JEV_API_KEY=jev-api-key:latest` to your usual `gcloud run deploy` command (deploy from a clean copy of the committed branch, as in DEPLOY_CLOUD_RUN.md, so the committed `player_pool_2026-27.json` ships with it). Without the key the page still works and falls back to the plain ranking.

**Manual leagues on Cloud Run.** They are stored in Firestore (collection `manual_leagues`, one document per league), so they survive restarts and redeploys. This switches on by itself when the app runs on Cloud Run (Cloud Run sets `K_SERVICE`); locally they stay as JSON files under `src/appl/data/draft/manual/`. Set `MANUAL_LEAGUE_STORE=file` or `=firestore` to force one. It uses the same `fantasy-app` service account and `roles/datastore.user` as the chat, so no new setup is needed, and changes run in Firestore transactions. Verified on the live service on 2026-10-08: a league created there was still in Firestore after a redeploy. (Leagues created before that, on the old file storage, were lost when the server was replaced.)

Known limits: the ranker covers the 9 standard categories only. Fuzzy name matching (similarity 0.88) is untested against Yahoo's real spellings, so the page warns when a drafted player has no stats match. The simulator's bots draft by z-score sum plus noise, which is only a rough stand-in for a real league.
