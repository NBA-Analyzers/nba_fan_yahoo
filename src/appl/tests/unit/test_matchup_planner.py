"""This week's matchup plan: live scoreboard, days, streamers and the things to do."""

from datetime import date

import pytest

from appl.draft.ranker import DraftRanker
from appl.season import snapshot as snapshots
from appl.season.analyzer import SeasonAnalyzer
from appl.season.matchup_planner import MatchupPlanner
from appl.season.schedule import Schedule
from appl.season.snapshot import MatchWeek
from appl.tests.unit.test_draft import _name, _player

MON, TUE, WED, THU, FRI, SAT = (date(2026, 10, d) for d in (12, 13, 14, 15, 16, 17))
TEAMS = ["LAL", "BOS", "NYK", "MIA", "DEN"]
POSITIONS = ["PG", "SG", "SF", "PF", "C"]


def schedule(days: dict[date, list[str]]) -> Schedule:
    """date -> the teams that play that day."""
    return Schedule({d.isoformat(): [{"home_team": t, "away_team": "ZZZ"} for t in teams]
                     for d, teams in days.items()})


# Everyone plays Wednesday; only LAL and BOS play Thursday; then the rest of the week
# the twins' teams play every day but Saturday.
WEEK = schedule({
    MON: TEAMS, TUE: TEAMS, WED: TEAMS + ["OKC"], THU: ["LAL", "BOS", "PHX"],
    FRI: TEAMS, date(2026, 10, 18): TEAMS,
})


def build(*, today=WED, live=None, sched=WEEK, slots=None, injuries=None, punts=None, hurt_mine=None):
    """My roster (team 0) and the opponent's (team 1) are twins: the same stats and
    NBA teams under different names, so the only differences are the ones a test adds."""
    pool, mine, theirs = [], [], []
    for i, (team, pos) in enumerate(zip(TEAMS, POSITIONS)):
        a = _player(_name("Alpha", i), pos in ("PF", "C"), i)
        a.update(team=team, pos=pos, GP=70)
        b = {**a, "name": _name("Bravo", i), "nba_id": 500 + i}
        if hurt_mine == i:  # one of mine is much weaker than his twin
            a.update(PTS=2.0, REB=1.0, AST=0.5, STL=0.1, BLK=0.1, FG3M=0.0)
        pool += [a, b]
        mine.append(a["name"])
        theirs.append(b["name"])
    fillers = [_player(_name("Mid", i), i % 2 == 0, 40 + i) for i in range(10)]
    for p in fillers:
        p.update(team="XXX", GP=70)
    pool += fillers
    # Two strong free agents: one plays only Wednesday, the other only Thursday
    for name, team, i in (("Stream Wed", "OKC", 80), ("Stream Thu", "PHX", 81)):
        fa = _player(_name("Free", i), True, i)
        fa.update(name=name, team=team, pos="PG", GP=70, PTS=30.0, REB=11.0, AST=8.0, STL=2.0, BLK=1.5, FG3M=3.0)
        pool.append(fa)
    pool += [dict(_player(_name("Rest", i), i % 2 == 0, 60 + i), team="XXX", GP=70) for i in range(12)]

    ranker = DraftRanker(pool, num_teams=4, roster_size=5)
    rosters = [mine, theirs, [p["name"] for p in fillers[:5]], [p["name"] for p in fillers[5:]]]
    week = MatchWeek(number=3, start=MON, end=date(2026, 10, 18), live=live or {})
    snap = snapshots.LeagueSnapshot(
        "t", "Test", ranker.categories, ["Me", "Them", "C", "D"], 0, rosters,
        slots=slots or {}, injuries=injuries or {}, scoring="h2h", opponent=1, week=week)
    analyzer = SeasonAnalyzer(ranker, snap, punts=punts, schedule=sched, today=today, opponent=1)
    return MatchupPlanner(analyzer), analyzer, ranker


def rows(planner):
    return {r["category"]: r for r in planner.scoreboard()}


# ---------- no opponent / no schedule ----------
def test_nothing_without_an_opponent():
    planner, analyzer, _ = build()
    analyzer.opponent = None
    planner = MatchupPlanner(analyzer)
    assert planner.scoreboard() == [] and planner.days() == [] and planner.plan() == []
    report = planner.report()
    assert report["available"] is False and report["week"]["start"] == MON.isoformat()
    # Same shape as an available report, so a page can loop over every section
    assert set(report) == {"available", "week", "summary", "scoreboard", "days", "streamers", "plan"}
    assert report["summary"] is None and report["scoreboard"] == report["days"] == report["plan"] == []


def test_without_a_schedule_the_default_games_are_used_and_there_are_no_days():
    planner, _, _ = build(sched=Schedule({}))
    assert planner.days() == [] and planner.streamers() == []
    summary = planner.summary()
    assert summary["scheduled"] is False
    assert summary["player_games_left"]["mine"] == 12.5  # 5 players * 3.5 games * 5 of 7 days left


# ---------- the scoreboard ----------
def test_twins_with_no_scores_are_toss_ups_and_the_whole_week_is_projected():
    planner, _, ranker = build()
    board = planner.scoreboard()
    assert [r["category"] for r in board] == ranker.categories
    assert all(not r["known"] and r["mine_so_far"] is None for r in board)
    assert all(r["win_prob"] == 0.5 and r["verdict"] == "toss-up" and r["stance"] == "chase" for r in board)
    assert any(t["kind"] == "note" for t in planner.plan())


def test_live_stats_are_added_to_the_rest_of_the_week():
    live = {0: {"PTS": 550.0}, 1: {"PTS": 400.0}}
    planner, _, _ = build(live=live)
    pts = rows(planner)["PTS"]
    assert pts["known"] and pts["mine_so_far"] == 550.0 and pts["theirs_so_far"] == 400.0
    assert pts["mine"] == round(550.0 + pts["mine_rest"], 1)
    assert pts["win_prob"] > 0.7 and pts["verdict"] in ("win", "lean win")
    small = rows(build(live={0: {"PTS": 420.0}, 1: {"PTS": 400.0}})[0])["PTS"]
    assert 0.5 < small["win_prob"] < pts["win_prob"] and small["verdict"] == "toss-up"
    assert not rows(planner)["REB"]["known"]  # nothing reported for it


def test_a_category_is_unknown_unless_both_sides_report_it():
    planner, _, _ = build(live={0: {"PTS": 400.0}, 1: {}})
    assert not rows(planner)["PTS"]["known"]


def test_percentages_use_makes_and_attempts_so_far():
    live = {0: {"FGM": 100.0, "FGA": 200.0}, 1: {"FGM": 90.0, "FGA": 200.0}}
    planner, _, _ = build(live=live)
    fg = rows(planner)["FG%"]
    assert fg["known"] and fg["mine_so_far"] == 0.5 and fg["theirs_so_far"] == 0.45
    assert fg["mine"] > fg["theirs"] and fg["win_prob"] > 0.5


def test_the_same_lead_is_safer_late_in_the_week():
    live = {0: {"PTS": 400.0}, 1: {"PTS": 380.0}}
    early = rows(build(live=live, today=TUE)[0])["PTS"]["win_prob"]
    late = rows(build(live=live, today=SAT)[0])["PTS"]["win_prob"]
    assert 0.5 < early < late


def test_after_the_week_ends_the_scores_decide():
    live = {0: {"PTS": 400.0, "TOV": 60.0}, 1: {"PTS": 380.0, "TOV": 50.0}}
    planner, _, _ = build(live=live, today=date(2026, 10, 19))
    board = rows(planner)
    assert planner.rest_days == 0
    assert board["PTS"]["win_prob"] == 1.0
    assert board["TO"]["win_prob"] == 0.0  # fewer turnovers wins
    assert board["PTS"]["mine"] == 400.0


def test_turnovers_are_won_by_having_fewer():
    live = {0: {"TOV": 40.0}, 1: {"TOV": 60.0}}
    assert rows(build(live=live)[0])["TO"]["win_prob"] > 0.5


def test_punted_categories_are_shown_but_not_counted():
    planner, _, ranker = build(punts=["BLK"])
    blk = rows(planner)["BLK"]
    assert blk["punted"] and blk["stance"] == "punted"
    assert planner.summary()["categories"] == len(ranker.categories) - 1
    assert all(t.get("category") != "BLK" for t in planner.plan())


def test_injured_players_lose_their_games():
    healthy = build()[0].summary()["player_games_left"]["mine"]
    hurt = build(injuries={_name("Alpha", 0): "out"})[0].summary()["player_games_left"]["mine"]
    assert hurt < healthy
    # LAL plays Wed, Thu, Fri and Sun from Wednesday on
    assert healthy - hurt == 4


def test_the_record_adds_up():
    summary = build(live={0: {"PTS": 500.0, "REB": 10.0}, 1: {"PTS": 300.0, "REB": 200.0}})[0].summary()
    record = summary["record"]
    assert record["wins"] + record["losses"] + record["ties"] == summary["categories"]
    assert 0 <= summary["expected_wins"] <= summary["categories"]


# ---------- the days ----------
SLOTS = {"PG": 1, "Util": 2}


def test_days_count_who_plays_and_the_slots_left():
    planner, _, _ = build(slots=SLOTS)
    days = {d["day"]: d for d in planner.days()}
    assert [d["day"] for d in planner.days()] == ["Wed", "Thu", "Fri", "Sat", "Sun"]
    assert days["Wed"]["mine"] == 5 and days["Wed"]["starters"] == 3 and days["Wed"]["open_slots"] == 0
    assert days["Thu"]["mine"] == 2 and days["Thu"]["starters"] == 2 and days["Thu"]["open_slots"] == 1
    assert days["Sat"]["mine"] == 0 and days["Sat"]["open_slots"] == 3


def test_a_day_with_more_players_than_slots_names_who_to_sit():
    planner, analyzer, _ = build(slots=SLOTS, hurt_mine=2)
    wed = next(d for d in planner.days() if d["day"] == "Wed")
    assert len(wed["sit"]) == 2
    playing = planner._playing(0, WED)
    sat = [p for p in playing if p["name"] in wed["sit"]]
    kept = [p for p in playing if p["name"] not in wed["sit"]]
    assert max(planner._play_value(p) for p in sat) <= min(planner._play_value(p) for p in kept)
    assert _name("Alpha", 2) in wed["sit"]  # the weak one
    assert next(d for d in planner.days() if d["day"] == "Thu")["sit"] == []


def test_unknown_slots_leave_the_slot_numbers_empty():
    wed = next(d for d in build()[0].days() if d["day"] == "Wed")
    assert wed["mine"] == 5 and wed["starters"] is None and wed["open_slots"] is None and wed["sit"] == []


def test_days_are_only_the_ones_left():
    planner, _, _ = build(slots=SLOTS, today=FRI)
    assert [d["day"] for d in planner.days()] == ["Fri", "Sat", "Sun"]


# ---------- streamers ----------
def test_a_streamer_only_counts_on_days_there_is_a_slot():
    planner, _, _ = build(slots=SLOTS)
    names = {s["name"]: s for s in planner.streamers()}
    assert "Stream Wed" not in names  # plays only Wednesday, when every slot is full
    thu = names["Stream Thu"]
    assert thu["days"] == ["Thu"] and thu["games"] == 1 and thu["score"] > 0


def test_every_game_counts_when_slots_are_unknown():
    names = {s["name"] for s in build()[0].streamers()}
    assert {"Stream Wed", "Stream Thu"} <= names


def test_the_best_streamers_come_first():
    scores = [s["score"] for s in build(slots=SLOTS)[0].streamers()]
    assert scores == sorted(scores, reverse=True)


# ---------- the plan ----------
def test_the_plan_leads_with_injuries_then_bench_and_stream_moves():
    planner, _, _ = build(slots=SLOTS, injuries={_name("Alpha", 4): "out"})
    kinds = [t["kind"] for t in planner.plan()]
    assert kinds[0] == "injury"
    assert kinds.index("injury") < kinds.index("stream")
    stream = next(t for t in planner.plan() if t["kind"] == "stream")
    assert "Stream Thu" in stream["text"] and "Thu" in stream["text"]


def test_the_plan_chases_protects_and_concedes_by_the_odds():
    live = {0: {"PTS": 900.0, "REB": 10.0, "AST": 100.0}, 1: {"PTS": 300.0, "REB": 400.0, "AST": 100.0}}
    plan = build(live=live)[0].plan()
    stance = {t["category"]: t["kind"] for t in plan if "category" in t}
    assert stance["PTS"] == "protect" and stance["REB"] == "concede" and stance["AST"] == "chase"
    order = [t["kind"] for t in plan if "category" in t]
    assert order.index("protect") > order.index("chase") and order.index("concede") > order.index("chase")
    assert order.count("chase") == 7  # AST and the six nobody has scored in


def test_the_plan_mentions_the_opponents_injuries():
    plan = build(injuries={_name("Bravo", 1): "out"})[0].plan()
    assert any(t["kind"] == "opponent" and _name("Bravo", 1) in t["text"] for t in plan)


# ---------- report ----------
def test_the_report_has_every_section():
    report = build(slots=SLOTS, live={0: {"PTS": 400.0}, 1: {"PTS": 380.0}})[0].report()
    assert report["available"] is True
    assert set(report) == {"available", "week", "summary", "scoreboard", "days", "streamers", "plan"}
    assert report["week"] == {"number": 3, "start": "2026-10-12", "end": "2026-10-18", "today": "2026-10-14"}
    assert report["summary"]["opponent"]["name"] == "Them"
    assert report["summary"]["live"] is True and report["summary"]["days_left"] == 5


@pytest.mark.parametrize("today", [MON, WED, SAT, date(2026, 10, 18), date(2026, 10, 25)])
def test_every_day_of_the_week_produces_a_report(today):
    report = build(slots=SLOTS, today=today)[0].report()
    assert report["available"] and len(report["scoreboard"]) == 9
