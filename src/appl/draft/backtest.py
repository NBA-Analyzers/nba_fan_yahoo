"""
Backtest for player-value models: project a finished season from the seasons before it
and compare with what actually happened.

A model is a function  (history, projections) -> pool,  where history is the per-game lines
of the seasons before the target, newest first ([{player_id: line}, ...]), projections are
ESPN's preseason projections for the target ({player_id: line}, empty when not fetched),
and pool is a list of player dicts like the draft pool. `evaluate` ranks both pools with the real DraftRanker
and reports how close the projected order is to the actual one.

Run against real seasons (needs ESPN or nba_api):
    python -m appl.draft.backtest 2025-26 2024-25
"""

import argparse
import json
import logging
import tempfile
from pathlib import Path
from statistics import mean
from typing import Callable

from ..ingest.season import previous_season
from .player_pool import add_projections, blend_seasons
from .ranker import DraftRanker

logger = logging.getLogger(__name__)

# Same weights the live pool uses today (draft/player_pool.py SOURCE_SEASONS)
BASELINE_WEIGHTS = [0.7, 0.3]
HISTORY_SEASONS = 4
MIN_ACTUAL_GAMES = 30  # only judge players who played enough for the target to mean something
TOP_N = 150
STAT_COLUMNS = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M"]

Model = Callable[[list[dict], dict[int, dict]], list[dict]]


def baseline_model(history: list[dict], projections: dict[int, dict]) -> list[dict]:
    """The last two seasons, 0.7 / 0.3, history only."""
    return blend_seasons(list(zip(history, BASELINE_WEIGHTS)))


def projections_model(history: list[dict], projections: dict[int, dict]) -> list[dict]:
    """The pool as it is built today: the baseline plus projected players it lacks."""
    return add_projections(baseline_model(history, projections), projections)


MODELS: dict[str, Model] = {"baseline": baseline_model, "projections": projections_model}


def lines_to_pool(lines: dict[int, dict]) -> list[dict]:
    return [{"nba_id": pid, **line} for pid, line in lines.items()]


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties share their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    """Rank correlation of two equal-length lists (1 = same order). 0 when undefined."""
    if len(a) < 2 or len(a) != len(b):
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0.0


def _scores(pool: list[dict], categories: list[str] | None) -> dict[str, tuple[float, dict]]:
    """key -> (sum of z, player row) for everyone the ranker keeps."""
    ranker = DraftRanker(pool, categories=categories)
    return {p["key"]: (sum(p["z"].values()), p) for p in ranker.players}


def evaluate(predicted: list[dict], actual: list[dict], *, top_n: int = TOP_N,
             min_actual_games: float = MIN_ACTUAL_GAMES,
             categories: list[str] | None = None) -> dict:
    """How well `predicted` (a pool built before the season) matches `actual` (the season's
    real per-game lines). All players are matched by normalized name."""
    pred = _scores(predicted, categories)
    act = {k: v for k, v in _scores(actual, categories).items()
           if v[1]["GP"] >= min_actual_games}

    actual_top = sorted(act, key=lambda k: act[k][0], reverse=True)[:top_n]
    n = len(actual_top)
    pred_top = sorted(pred, key=lambda k: pred[k][0], reverse=True)[:n]

    both = [k for k in act if k in pred]
    missing = [act[k][1]["name"] for k in actual_top if k not in pred]
    stat_mae = {
        col: round(mean(abs(pred[k][1][col] - act[k][1][col]) for k in both), 3)
        for col in STAT_COLUMNS
    } if both else {}

    return {
        "players_compared": len(both),
        "spearman": round(spearman([pred[k][0] for k in both], [act[k][0] for k in both]), 4),
        "top_n": n,
        "top_n_overlap": round(len(set(pred_top) & set(actual_top)) / n, 4) if n else 0.0,
        # Actual top players the model has no row for (rookies, new arrivals)
        "missing_from_top_n": len(missing),
        "missing_names": missing,
        "stat_mae": stat_mae,
    }


# --- real data -----------------------------------------------------------------

def _cache_path(cache_dir: Path, season: str, kind: str = "season") -> Path:
    return cache_dir / f"{kind}_{season}.json"


def fetch_season_cached(season: str, fetch: Callable[[str], dict[int, dict]],
                        cache_dir: Path, kind: str = "season") -> dict[int, dict]:
    path = _cache_path(cache_dir, season, kind)
    if path.exists():
        return {int(pid): line for pid, line in json.loads(path.read_text("utf-8")).items()}
    lines = fetch(season)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lines), encoding="utf-8")
    return lines


def run_backtest(target: str, fetch: Callable[[str], dict[int, dict]],
                 models: dict[str, Model] | None = None, *, history_seasons: int = HISTORY_SEASONS,
                 cache_dir: Path | None = None,
                 fetch_projections: Callable[[str], dict[int, dict]] | None = None,
                 **evaluate_kwargs) -> dict[str, dict]:
    """Project `target` with each model from the seasons before it (and ESPN's preseason
    projections for it, when `fetch_projections` is given); metrics per model."""
    cache_dir = cache_dir or Path(tempfile.gettempdir()) / "nba_backtest_cache"
    get = lambda s: fetch_season_cached(s, fetch, cache_dir)  # noqa: E731
    history = [get(previous_season(target, i)) for i in range(1, history_seasons + 1)]
    actual = lines_to_pool(get(target))
    projections = (fetch_season_cached(target, fetch_projections, cache_dir, "projections")
                   if fetch_projections else {})
    return {name: evaluate(model(history, projections), actual, **evaluate_kwargs)
            for name, model in (models or MODELS).items()}


def format_report(target: str, results: dict[str, dict]) -> str:
    lines = [f"Backtest {target}  (top {next(iter(results.values()))['top_n']} by actual value)",
             f"{'model':<14}{'spearman':>10}{'top-N overlap':>15}{'missing':>9}"]
    for name, r in results.items():
        lines.append(f"{name:<14}{r['spearman']:>10.3f}{r['top_n_overlap']:>15.1%}"
                     f"{r['missing_from_top_n']:>9}")
    for name, r in results.items():
        if r["missing_names"]:
            lines.append(f"\n{name}: top players with no projection: "
                         + ", ".join(r["missing_names"][:15]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    from .player_pool import _fetch_projections, _fetch_season

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="+", help="seasons to project, e.g. 2025-26")
    parser.add_argument("--history", type=int, default=HISTORY_SEASONS)
    parser.add_argument("--models", nargs="*", default=None, help=f"of {list(MODELS)}")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    models = {m: MODELS[m] for m in args.models} if args.models else MODELS
    for target in args.targets:
        results = run_backtest(target, _fetch_season, models, history_seasons=args.history,
                               fetch_projections=_fetch_projections)
        print(format_report(target, results), end="\n\n")


if __name__ == "__main__":
    main()
