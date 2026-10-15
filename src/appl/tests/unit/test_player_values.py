"""Backtest harness, plus tests for the known gaps in how player values are built.

The xfail(strict=True) tests describe behavior we want and don't have yet. Each one fails
today; when its fix lands the test passes, strict mode flags it, and the marker comes off.
"""

import pytest

from appl.draft import backtest, player_pool
from appl.draft.ranker import CATEGORIES, DraftRanker
from appl.tests.unit.test_draft import _line, _name, _player


def _veterans(count=200):
    players = [_player(_name("Big", i), True, i) for i in range(count // 2)]
    players += [_player(_name("Guard", i), False, 1000 + i) for i in range(count // 2)]
    return players


def _season_lines(players, gp=70):
    return {p["nba_id"]: {**{k: v for k, v in p.items() if k != "nba_id"}, "GP": gp}
            for p in players}


# --- backtest harness ----------------------------------------------------------

def test_spearman_is_one_for_same_order_minus_one_for_reversed_and_handles_ties():
    assert backtest.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert backtest.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert backtest.spearman([1, 1, 1], [1, 2, 3]) == 0.0
    assert backtest.spearman([1], [1]) == 0.0


def test_a_perfect_projection_scores_perfectly():
    actual = _veterans()
    result = backtest.evaluate(actual, actual, top_n=50)
    assert result["spearman"] == pytest.approx(1.0)
    assert result["top_n_overlap"] == 1.0
    assert result["missing_from_top_n"] == 0
    assert all(error == 0 for error in result["stat_mae"].values())


def test_players_the_projection_lacks_are_reported_as_missing():
    actual = _veterans()
    star = {**_player("Rookie Star", True, 5000, gp=70), "PTS": 45.0, "REB": 14.0, "AST": 9.0,
            "STL": 2.5, "BLK": 2.5, "FG3M": 3.5}
    result = backtest.evaluate(actual, actual + [star], top_n=50)
    assert "Rookie Star" in result["missing_names"]
    assert result["missing_from_top_n"] >= 1


def test_only_players_with_enough_actual_games_are_judged():
    actual = _veterans() + [_player("Short Season", True, 6000, gp=20)]
    result = backtest.evaluate(_veterans(), actual, top_n=50, min_actual_games=30)
    assert "Short Season" not in result["missing_names"]


def test_run_backtest_projects_the_target_from_earlier_seasons_and_caches_downloads(tmp_path):
    players = _veterans()
    calls = []

    def fetch(season):
        calls.append(season)
        return _season_lines(players)

    first = backtest.run_backtest("2025-26", fetch, cache_dir=tmp_path, top_n=50)
    assert set(first) == {"baseline", "projections"}
    assert first["baseline"]["spearman"] == pytest.approx(1.0)
    # target + 4 history seasons, each downloaded once
    assert sorted(calls) == sorted({"2025-26", "2024-25", "2023-24", "2022-23", "2021-22"})

    backtest.run_backtest("2025-26", fetch, cache_dir=tmp_path, top_n=50)
    assert len(calls) == 5


def test_the_projections_model_fills_in_a_rookie_the_history_lacks(tmp_path):
    players = _veterans()
    star = {**_player("Rookie Star", True, 5000, gp=70), "PTS": 45.0, "REB": 14.0, "AST": 9.0,
            "STL": 2.5, "BLK": 2.5, "FG3M": 3.5}

    def fetch(season):
        return _season_lines(players + [star] if season == "2025-26" else players)

    results = backtest.run_backtest(
        "2025-26", fetch, cache_dir=tmp_path, top_n=50,
        fetch_projections=lambda season: _season_lines([star]))
    assert "Rookie Star" in results["baseline"]["missing_names"]
    assert results["projections"]["missing_from_top_n"] == 0


def test_report_lists_each_model():
    players = _veterans()
    results = {"baseline": backtest.evaluate(players, players, top_n=50)}
    text = backtest.format_report("2025-26", results)
    assert "baseline" in text and "spearman" in text


# --- known gaps (see the module docstring) -------------------------------------

@pytest.mark.xfail(strict=True, reason="rookies get raw current stats with no shrinkage")
def test_a_rookies_hot_first_game_is_shrunk_toward_a_prior():
    prior = [{**_player("Vet One", True, 1), "GP": 70}]
    hot = {**_line(1, 40.0), "name": "Hot Rookie"}
    veteran = {**_line(3, 20.0), "name": "Vet One"}
    pool = player_pool.blend_current(prior, {1: veteran, 900: hot})
    rookie = next(p for p in pool if p["name"] == "Hot Rookie")
    assert rookie["PTS"] < 20


def test_a_star_hurt_last_season_stays_in_the_pool():
    star = {**_line(10, 28.0), "name": "Hurt Star", "FGA": 20, "FGM": 11}
    old = {**_line(70, 28.0), "name": "Hurt Star", "FGA": 20, "FGM": 11}
    others = _season_lines(_veterans())
    pool = player_pool.blend_seasons(
        [({**others, 5000: star}, 0.7), ({**others, 5000: old}, 0.3)]
    )
    assert DraftRanker(pool).find("Hurt Star") is not None


def test_games_count_a_missed_season_as_zero_but_not_seasons_before_a_debut():
    others = _season_lines(_veterans(10))
    hurt, old = {**_line(10, 20.0), "name": "Hurt"}, {**_line(70, 20.0), "name": "Hurt"}
    sat_out = {**_line(60, 20.0), "name": "Sat Out"}
    sophomore = {**_line(40, 20.0), "name": "Sophomore"}
    bench, bench_old = {**_line(15, 8.0), "name": "Bench"}, {**_line(5, 8.0), "name": "Bench"}
    pool = player_pool.blend_seasons([
        ({**others, 9001: hurt, 9003: sophomore, 9004: bench}, 0.7),
        ({**others, 9001: old, 9002: sat_out, 9004: bench_old}, 0.3),
    ])
    games = {p["name"]: p["GP"] for p in pool}
    assert games["Hurt"] == pytest.approx(0.7 * 10 + 0.3 * 70)
    assert games["Sat Out"] == pytest.approx(0.3 * 60)
    assert games["Sophomore"] == pytest.approx(40)
    # An older, shorter season never pulls a player below last season's games
    assert games["Bench"] == 15


# --- projections for players with no history ------------------------------------

def _projection(name, pts=18.0, gp=70.0):
    return {**_line(gp, pts), "name": name, "team": "SA", "pos": "F"}


def test_rookies_missing_from_history_are_added_from_projections():
    history = player_pool.blend_seasons([(_season_lines(_veterans()), 1.0)])
    pool = player_pool.add_projections(history, {9001: _projection("Top Rookie", pts=24.0)})
    rookie = next(p for p in pool if p["name"] == "Top Rookie")
    assert rookie["projected"] is True and rookie["nba_id"] == 9001
    ranker = DraftRanker(pool)
    assert ranker.find("Top Rookie") is not None


def test_projections_never_replace_a_player_the_history_covers():
    history = player_pool.blend_seasons([(_season_lines(_veterans(10)), 1.0)])
    vet = history[0]
    pool = player_pool.add_projections(history, {
        vet["nba_id"]: _projection(vet["name"], pts=99.0),        # same id
        555: _projection(vet["name"].upper() + " Jr.", pts=99.0),  # same player, other spelling
    })
    assert len(pool) == len(history)
    assert all(p["PTS"] != 99.0 for p in pool)


def test_the_pool_is_still_built_when_projections_are_down(monkeypatch, tmp_path):
    lines = _season_lines(_veterans(10))
    monkeypatch.setattr(player_pool, "_store", lambda: player_pool.LocalDatasetStore(tmp_path))
    monkeypatch.setattr(player_pool, "_fetch_season", lambda season: lines)

    def down(season):
        raise RuntimeError("ESPN fantasy is down")

    monkeypatch.setattr(player_pool, "_fetch_projections", down)
    assert len(player_pool.build_player_pool()) == 10


def test_the_pool_build_adds_projected_rookies(monkeypatch, tmp_path):
    lines = _season_lines(_veterans(10))
    monkeypatch.setattr(player_pool, "_store", lambda: player_pool.LocalDatasetStore(tmp_path))
    monkeypatch.setattr(player_pool, "_fetch_season", lambda season: lines)
    monkeypatch.setattr(player_pool, "_fetch_projections",
                        lambda season: {9001: _projection("Top Rookie")})
    assert "Top Rookie" in {p["name"] for p in player_pool.build_player_pool()}


def test_a_projected_rookies_first_games_are_blended_with_his_projection():
    prior = [{**_projection("Top Rookie", pts=15.0), "nba_id": 9001, "projected": True}]
    pool = player_pool.blend_current(prior, {1: {**_line(1, 40.0), "name": "Top Rookie"}})
    assert len(pool) == 1
    assert 15.0 < pool[0]["PTS"] < 20.0


def test_espn_projections_are_parsed_into_pool_lines():
    from appl.ingest.sources.espn import parse_espn_projections

    stats = {"0": 20.1, "1": 0.6, "2": 1.1, "3": 2.8, "6": 4.9, "11": 2.5, "13": 7.2,
             "14": 15.0, "15": 4.9, "16": 6.0, "17": 0.7, "40": 32.2, "42": 72.0}
    payload = {"players": [
        {"player": {"id": 5, "fullName": "AJ Dybantsa", "proTeamId": 26, "defaultPositionId": 3,
                    "stats": [{"id": "002026", "averageStats": {"0": 1.0}},
                              {"id": "102027", "averageStats": stats}]}},
        {"player": {"id": 6, "fullName": "No Projection", "stats": [{"id": "102026",
                                                                    "averageStats": stats}]}},
        # ESPN leaves out stats projected at zero (a center's threes)
        {"player": {"id": 7, "fullName": "Zach Edey", "stats": [{"id": "102027", "averageStats": {
            k: v for k, v in stats.items() if k != "17"}}]}},
        {"player": {"id": 8, "fullName": "No Games", "stats": [{"id": "102027", "averageStats": {
            k: v for k, v in stats.items() if k != "42"}}]}},
    ]}
    lines = parse_espn_projections(payload, 2027)
    assert sorted(lines) == [5, 7]
    assert lines[7]["FG3M"] == 0.0
    assert lines[5]["name"] == "AJ Dybantsa" and lines[5]["team"] == "UTAH"
    assert lines[5]["pos"] == "F"
    assert lines[5]["PTS"] == 20.1 and lines[5]["GP"] == 72.0 and lines[5]["TOV"] == 2.5


@pytest.mark.xfail(strict=True, reason="nickname spellings aren't matched")
def test_nickname_spellings_resolve_to_the_same_player():
    pool = _veterans() + [_player("Nicolas Claxton", True, 998)]
    assert DraftRanker(pool).find("Nic Claxton") is not None


@pytest.mark.xfail(strict=True, reason="fuzzy matching merges different first names")
def test_similar_names_of_different_players_are_not_merged():
    pool = _veterans() + [_player("Jalen Williams", False, 997)]
    ranker = DraftRanker(pool)
    assert ranker.find("Jalen Williams") is not None
    assert ranker.find("Jaylin Williams") is None


@pytest.mark.xfail(strict=True, reason="in-season rows are matched by exact name only")
def test_a_renamed_player_isnt_duplicated_when_this_seasons_stats_arrive():
    prior = [{**_player("Nic Claxton", True, 1), "GP": 70}]
    current = {55: {**_line(10, 12.0), "name": "Nicolas Claxton"}}
    pool = player_pool.blend_current(prior, current)
    assert len(pool) == 1


@pytest.mark.xfail(strict=True, reason="availability is multiplied onto negative scores too")
def test_missing_games_never_improves_a_below_average_player():
    ranker = DraftRanker(_veterans())
    worst = min(ranker.players, key=lambda p: sum(p["z"].values()))
    weights = {c: 1.0 for c in CATEGORIES}
    assert sum(worst["z"].values()) < 0
    healthy = ranker._fit({**worst, "GP": 70}, weights)
    injured = ranker._fit({**worst, "GP": 15}, weights)
    assert injured <= healthy
