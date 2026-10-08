"""
Mock snake drafts to compare pick strategies, e.g. "does Jev beat the ranker?".

Bots draft by consensus rank (the ranker's no-punt z-sum) plus noise, so they
behave like a typical league. One seat uses the strategy under test. Teams are
then scored head-to-head: for each opponent and category, the bigger sum of
player z-scores wins (turnovers are already inverted in the z-scores).

Run from src/:
    python -m appl.draft.mock_eval --synthetic                 # ranker only
    python -m appl.draft.mock_eval --punts "FT%" --seeds 20    # real pool cache
    python -m appl.draft.mock_eval --jev --seeds 5             # include Jev (uses API calls)
"""

import argparse
import random
from statistics import mean

from . import jev_chooser
from .player_pool import load_player_pool
from .ranker import CATEGORIES, DraftRanker

BOT_NOISE_RANKS = 6.0  # std-dev of a bot's mistake, in ranks


def synthetic_pool(seed: int = 0, size: int = 220) -> list[dict]:
    rnd = random.Random(seed)
    pool = []
    for i in range(size):
        big = i % 3 == 0
        fga, fta = rnd.uniform(6, 18), rnd.uniform(3, 8) if big else rnd.uniform(1, 5)
        fgp = rnd.uniform(0.5, 0.62) if big else rnd.uniform(0.42, 0.48)
        ftp = rnd.uniform(0.5, 0.65) if big else rnd.uniform(0.8, 0.92)
        pool.append({
            "nba_id": i, "name": f"Player {chr(65 + i // 26)}{chr(97 + i % 26)}",
            "team": "SYN", "GP": rnd.randint(40, 78), "MIN": rnd.uniform(20, 36),
            "PTS": rnd.uniform(8, 27),
            "REB": rnd.uniform(7, 13) if big else rnd.uniform(2, 6),
            "AST": rnd.uniform(1, 4) if big else rnd.uniform(2, 9),
            "STL": rnd.uniform(0.3, 1.7),
            "BLK": rnd.uniform(0.8, 2.6) if big else rnd.uniform(0.1, 0.6),
            "TOV": rnd.uniform(0.8, 3.6),
            "FG3M": rnd.uniform(0, 0.6) if big else rnd.uniform(0.5, 3.6),
            "FGM": fga * fgp, "FGA": fga, "FTM": fta * ftp, "FTA": fta,
        })
    return pool


def _snake_order(num_teams: int, rounds: int) -> list[int]:
    order = []
    for rnd in range(rounds):
        seats = range(num_teams) if rnd % 2 == 0 else range(num_teams - 1, -1, -1)
        order.extend(seats)
    return order


def run_draft(
    ranker: DraftRanker,
    strategy: str,
    punts: list[str],
    seat: int,
    seed: int,
    num_teams: int = 12,
    rounds: int = 13,
    jev_client=None,
) -> dict:
    """Simulate one draft; `strategy` is baseline | ranker | jev."""
    rnd = random.Random(seed)
    consensus = {
        p["name"]: i + 1
        for i, p in enumerate(
            sorted(ranker.players, key=lambda p: sum(p["z"].values()), reverse=True)
        )
    }
    noisy = {n: r + rnd.gauss(0, BOT_NOISE_RANKS) for n, r in consensus.items()}
    teams: list[list[str]] = [[] for _ in range(num_teams)]
    taken: set[str] = set()
    stats = {"jev_calls": 0, "jev_agrees": 0, "jev_fallbacks": 0, "confidences": []}

    for team in _snake_order(num_teams, rounds):
        if team != seat:
            pick = min((n for n in noisy if n not in taken), key=noisy.get)
        elif strategy == "baseline":
            pick = ranker.rank(taken_names=list(taken), limit=1)[0]["name"]
        else:
            recs = ranker.rank(
                punts=punts, taken_names=list(taken),
                my_roster_names=teams[seat], limit=jev_chooser.SHORTLIST_SIZE,
            )
            pick = recs[0]["name"]
            if strategy == "jev":
                decision = jev_chooser.decide(
                    "assist", recs, teams[seat], punts, ranker.categories,
                    ranker.roster_profile(teams[seat]), client=jev_client,
                )
                stats["jev_calls"] += 1
                if decision and decision["source"] == "jev":
                    pick = decision["pick"]
                    stats["jev_agrees"] += decision["agrees_with_engine"]
                    stats["confidences"].append(decision["confidence"])
                else:
                    stats["jev_fallbacks"] += 1
        teams[team].append(pick)
        taken.add(pick)

    return {"teams": teams, "stats": stats}


def evaluate(ranker: DraftRanker, teams: list[list[str]], seat: int, punts: list[str]):
    totals = []
    for roster in teams:
        players = [ranker.find(n) for n in roster]
        totals.append({c: sum(p["z"][c] for p in players if p) for c in ranker.categories})
    mine, others = totals[seat], [t for i, t in enumerate(totals) if i != seat]
    wins = {c: sum(mine[c] > o[c] for o in others) / len(others) for c in ranker.categories}
    counted = [c for c in ranker.categories if c not in punts]
    return {
        "win_pct_all": mean(wins.values()),
        "win_pct_counted": mean(wins[c] for c in counted),
        "wins": wins,
    }


def compare(ranker, strategies, punts, seeds, seat, num_teams, jev_client=None):
    results = {}
    for strategy in strategies:
        rows = []
        for seed in range(seeds):
            draft = run_draft(ranker, strategy, punts, seat, seed, num_teams, jev_client=jev_client)
            rows.append({**evaluate(ranker, draft["teams"], seat, punts), **draft["stats"]})
        results[strategy] = rows
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--synthetic", action="store_true", help="use a made-up pool (no NBA data needed)")
    parser.add_argument("--punts", default="FT%", help="comma-separated categories to punt")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--seat", type=int, default=5, help="your draft slot, 1-based")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--jev", action="store_true", help="also run the Jev strategy (calls the API)")
    args = parser.parse_args()

    punts = [p for p in args.punts.split(",") if p]
    pool = synthetic_pool() if args.synthetic else load_player_pool()
    ranker = DraftRanker(pool, categories=CATEGORIES, num_teams=args.teams)

    strategies = ["baseline", "ranker"] + (["jev"] if args.jev else [])
    if args.jev and not jev_chooser.is_configured():
        raise SystemExit("--jev needs JEV_API_KEY in src/.env")
    results = compare(ranker, strategies, punts, args.seeds, args.seat - 1, args.teams)

    print(f"{args.seeds} drafts, seat {args.seat}/{args.teams}, punting {punts or 'nothing'}"
          f"{' (synthetic pool)' if args.synthetic else ''}")
    print(f"{'strategy':<10} {'cat win % (all 9)':>18} {'cat win % (counted)':>20}")
    for name, rows in results.items():
        print(f"{name:<10} {mean(r['win_pct_all'] for r in rows):>17.1%} "
              f"{mean(r['win_pct_counted'] for r in rows):>19.1%}")
    if "jev" in results:
        rows = results["jev"]
        calls = sum(r["jev_calls"] for r in rows)
        confs = [c for r in rows for c in r["confidences"]]
        print(f"\nJev: {calls} picks, fell back to the ranker on {sum(r['jev_fallbacks'] for r in rows)}, "
              f"agreed with the ranker on {sum(r['jev_agrees'] for r in rows)}, "
              f"mean confidence {mean(confs):.2f}" if confs else "\nJev: no successful calls")


if __name__ == "__main__":
    main()
