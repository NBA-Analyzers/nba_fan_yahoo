"""League analysis: power rankings, buy low / sell high, trade ideas and the playoff schedule."""

from datetime import date, timedelta

import pytest

from appl.draft.player_pool import normalize_name
from appl.draft.ranker import DraftRanker
from appl.season import snapshot as snapshots
from appl.season.analyzer import SeasonAnalyzer
from appl.season.league_analysis import BIG_MOVE, LeagueAnalysis
from appl.season.player_status import PlayerData
from appl.season.schedule import Schedule
from appl.tests.unit.test_season import POOL

TODAY = date(2026, 12, 2)  # a Wednesday


class FakeData:
    """Stands in for the nightly datasets: recent form by player name, and injuries."""

    def __init__(self, forms=None, injuries=None):
        self.forms = forms or {}
        self.injuries = injuries or {}

    def form(self, name):
        return self.forms.get(name)

    def injury_levels(self):
        return self.injuries


def form(p, scale=1.0, minutes=0.0, fg=None, games=6, window="last_14_days"):
    """A recent window shaped like PlayerData.form(): the season line with the counting
    stats scaled, minutes shifted and, when given, a different field-goal percentage."""
    fg_rate = fg if fg is not None else p["FGM"] / p["FGA"]
    w = {"games": games, "min": p["MIN"] + minutes, "pts": p["PTS"] * scale, "reb": p["REB"] * scale,
         "ast": p["AST"] * scale, "stl": p["STL"] * scale, "blk": p["BLK"] * scale, "tov": p["TOV"],
         "3pm": p["FG3M"] * scale, "fgm": p["FGA"] * fg_rate, "fga": p["FGA"], "ftm": p["FTM"], "fta": p["FTA"]}
    return {window: w, "season_min": p["MIN"], "minutes_trend": minutes}


def build(*, teams=6, size=8, injuries=None, schedule=None, today=TODAY, punts=None):
    """A snake draft of the best players, every NBA team unknown ("XXX")."""
    ranker = DraftRanker([dict(p) for p in POOL], num_teams=teams, roster_size=size)
    names = [p["name"] for p in sorted(ranker.players, key=lambda p: -sum(p["z"].values()))]
    rosters = [[] for _ in range(teams)]
    for i, name in enumerate(names[: teams * size]):
        rnd, pos = divmod(i, teams)
        rosters[pos if rnd % 2 == 0 else teams - 1 - pos].append(name)
    snap = snapshots.LeagueSnapshot("t", "L", ranker.categories, [f"T{i}" for i in range(teams)], 0, rosters,
                                    injuries=injuries or {})
    return SeasonAnalyzer(ranker, snap, punts, schedule=schedule, today=today)


def player(analyzer, team, i):
    return analyzer.players[team][i]


def analysis(analyzer, forms=None, injuries=None):
    return LeagueAnalysis(analyzer, FakeData(forms, injuries))


def names(rows):
    return [r["name"] for r in rows]


# ---------- the building blocks ----------
def test_the_ranker_scores_a_season_line_the_same_as_the_pool():
    ranker = DraftRanker(POOL, num_teams=6, roster_size=8)
    p = ranker.players[10]
    assert ranker.z_for(p) == pytest.approx(p["z"], abs=0.011)


def test_player_form_exposes_recent_makes_and_attempts():
    stats = {"Shooter": {"season": {"Minutes": 30.0}, "last_14_days": {
        "Games Played": 5, "Average Minutes": 31.0, "Field Goals Made": 7.0, "Field Goals Attempted": 15.0,
        "Free Throws Made": 3.0, "Free Throws Attempted": 4.0}}}
    w = PlayerData(stats=stats).form("Shooter")["last_14_days"]
    assert (w["fgm"], w["fga"], w["ftm"], w["fta"]) == (7.0, 15.0, 3.0, 4.0)


# ---------- buy low / sell high ----------
def test_a_hot_shooting_streak_on_the_same_minutes_is_a_sell_high():
    a = build()
    hot = player(a, 0, 1)
    rows = analysis(a, {hot["name"]: form(hot, scale=1.3, fg=0.60)}).buy_sell()
    row = next(r for r in rows["sell_high"] if r["name"] == hot["name"])
    assert row["verdict"] == "sell_high" and row["change"] >= BIG_MOVE
    assert "Shooting 60%" in row["reason"]
    assert row["owner"] == {"index": 0, "name": "T0"}


def test_more_minutes_while_a_teammate_is_out_is_a_sell_high():
    a = build()
    mine, star = player(a, 0, 2), player(a, 3, 0)
    mine["team"] = star["team"] = "BOS"
    data = {mine["name"]: form(mine, scale=1.4, minutes=7)}
    rows = analysis(a, data, injuries={star["name"]: "out"}).buy_sell()
    row = next(r for r in rows["sell_high"] if r["name"] == mine["name"])
    assert star["name"] in row["reason"] and "+7.0 minutes" in row["reason"]


def test_more_minutes_with_no_one_out_is_a_breakout_you_keep():
    a = build()
    mine = player(a, 0, 2)
    rows = analysis(a, {mine["name"]: form(mine, scale=1.4, minutes=7)}).buy_sell()
    assert mine["name"] not in names(rows["sell_high"])
    row = next(r for r in rows["hold"] if r["name"] == mine["name"])
    assert row["verdict"] == "breakout" and "bigger role" in row["reason"]


def test_a_rivals_breakout_is_a_target_and_so_is_a_free_agents():
    a = build()
    theirs = player(a, 2, 4)
    free = next(p for p in a.ranker.players if p["name"] not in a.snapshot.rostered())
    data = {theirs["name"]: form(theirs, scale=1.5, minutes=8), free["name"]: form(free, scale=1.8, minutes=10)}
    rows = analysis(a, data).buy_sell()
    by_name = {r["name"]: r for r in rows["breakouts"]}
    assert by_name[theirs["name"]]["owner"]["index"] == 2
    assert by_name[free["name"]]["owner"] is None  # on waivers


def test_a_rivals_slump_on_the_same_minutes_is_a_buy_low():
    a = build()
    theirs = player(a, 4, 0)
    rows = analysis(a, {theirs["name"]: form(theirs, scale=0.65, fg=0.36)}).buy_sell()
    row = next(r for r in rows["buy_low"] if r["name"] == theirs["name"])
    assert row["verdict"] == "buy_low" and row["change"] <= -BIG_MOVE
    assert row["owner"] == {"index": 4, "name": "T4"} and "slump" in row["reason"]
    assert row["recent_value"] < row["season_value"]


def test_buy_low_targets_are_measured_against_the_league_not_zero():
    a = build()
    values = sorted(sum(p["z"][c] for c in a.counted) for team in a.players for p in team)
    median = values[len(values) // 2]
    rivals = [p for t in range(1, 6) for p in a.players[t]]
    good = next(p for p in rivals if median <= sum(p["z"][c] for c in a.counted) < 0)
    poor = min(rivals, key=lambda p: sum(p["z"][c] for c in a.counted))
    data = {p["name"]: form(p, scale=0.6, fg=0.34) for p in (good, poor)}
    rows = analysis(a, data).buy_sell()
    assert names(rows["buy_low"]) == [good["name"]]  # below zero, but above the league's median


def test_your_own_slump_is_a_hold_not_a_sell():
    a = build()
    mine = player(a, 0, 0)
    rows = analysis(a, {mine["name"]: form(mine, scale=0.65, fg=0.36)}).buy_sell()
    assert mine["name"] in names(rows["hold"]) and mine["name"] not in names(rows["buy_low"])


def test_lost_minutes_is_fading_not_a_buy():
    a = build()
    theirs, mine = player(a, 4, 0), player(a, 0, 3)
    data = {theirs["name"]: form(theirs, scale=0.6, minutes=-8), mine["name"]: form(mine, scale=0.6, minutes=-8)}
    rows = analysis(a, data).buy_sell()
    assert theirs["name"] not in names(rows["buy_low"])
    assert names(rows["fading"]) == [mine["name"]]  # only your own players are worth a warning
    assert "fewer minutes" in rows["fading"][0]["reason"]


def test_small_moves_and_short_windows_are_ignored():
    a = build()
    calm, short = player(a, 0, 1), player(a, 0, 2)
    data = {calm["name"]: form(calm, scale=1.05), short["name"]: form(short, scale=1.6, games=2)}
    rows = analysis(a, data).buy_sell()
    assert not any(rows[k] for k in ("sell_high", "hold", "fading"))


def test_a_short_two_weeks_falls_back_to_the_last_thirty_days():
    a = build()
    p = player(a, 0, 1)
    data = form(p, scale=1.0, games=2)
    data.update(form(p, scale=1.3, fg=0.60, window="last_30_days"))
    row = analysis(a, {p["name"]: data}).buy_sell()["sell_high"][0]
    assert row["name"] == p["name"] and row["window"] == "last 30 days"


def test_the_categories_that_moved_most_come_first():
    a = build()
    p = player(a, 0, 1)
    row = analysis(a, {p["name"]: form(p, scale=1.0, fg=0.66)}).buy_sell()["sell_high"][0]
    assert row["moved"][0][0] == "FG%" and row["moved"][0][1] > 0


def test_without_form_data_there_is_nothing_to_say():
    a = build()
    rows = LeagueAnalysis(a, None).buy_sell()
    assert rows["available"] is False
    assert not any(rows[k] for k in ("sell_high", "buy_low", "hold", "breakouts", "fading"))


# ---------- trade ideas ----------
def test_trade_ideas_send_your_hot_player_for_their_cold_one():
    a = build()
    give, get = player(a, 0, 3), player(a, 4, 1)
    data = {give["name"]: form(give, scale=1.35, fg=0.58), get["name"]: form(get, scale=0.65, fg=0.36)}
    ideas = analysis(a, data).trade_ideas()
    assert ideas, "expected a sell-high for buy-low idea"
    idea = ideas[0]
    assert idea["give"] == give["name"] and idea["get"] == get["name"]
    assert idea["partner"] == {"index": 4, "name": "T4"} and idea["gain"] > 0 and idea["unit"] == "roto points"
    assert idea["their_view"] >= -0.75  # looks fair to them on recent form


def test_no_trade_ideas_without_both_sides():
    a = build()
    give = player(a, 0, 3)
    assert analysis(a, {give["name"]: form(give, scale=1.35, fg=0.58)}).trade_ideas() == []


# ---------- power rankings ----------
def test_power_rankings_cover_every_team_best_first():
    a = build()
    rows = LeagueAnalysis(a, None).power_rankings()
    assert [r["place"] for r in rows] == list(range(1, 7))
    assert [r["expected_wins"] for r in rows] == sorted((r["expected_wins"] for r in rows), reverse=True)
    assert sum(r["is_mine"] for r in rows) == 1
    # All-play is zero-sum: every category won by one team is lost by another
    assert sum(r["expected_wins"] for r in rows) == pytest.approx(6 * len(a.categories) / 2, abs=0.05)


def test_power_rankings_show_strengths_injuries_and_a_hot_roster():
    a = build()
    hurt = player(a, 2, 0)["name"]
    a._inj = {**a._inj, normalize_name(hurt): "out"}
    forms = {p["name"]: form(p, scale=1.35) for p in a.players[5]}
    rows = {r["index"]: r for r in analysis(a, forms).power_rankings()}
    assert rows[5]["form"] == "hot" and rows[0]["form"] is None
    assert rows[2]["injured"] == 1
    assert len(rows[0]["strengths"]) == 2 and len(rows[0]["weaknesses"]) == 2


# ---------- the playoff schedule ----------
def season_schedule(last_day: date, plays=lambda team, day: True):
    """Games every day from early December to `last_day`; `plays` picks who plays."""
    days = {}
    day = date(2026, 12, 1)
    while day <= last_day:
        games = [{"home_team": t, "away_team": "UTA"} for t in ("BOS", "LAL") if plays(t, day)]
        days[day.isoformat()] = games
        day += timedelta(days=1)
    return Schedule(days)


def test_the_playoffs_are_the_last_three_full_weeks():
    last = date(2027, 4, 14)  # a Wednesday: the final partial week does not count
    a = build(schedule=season_schedule(last))
    report = LeagueAnalysis(a, None).playoff_schedule()
    assert report["available"] is True
    assert [w["start"] for w in report["weeks"]] == ["2027-03-22", "2027-03-29", "2027-04-05"]
    assert [w["end"] for w in report["weeks"]][-1] == "2027-04-11"


def test_playoff_games_are_counted_per_player_and_team():
    sunday = date(2027, 4, 11)
    # Boston plays every day, the Lakers only on Mondays
    a = build(schedule=season_schedule(sunday, lambda t, d: t == "BOS" or d.weekday() == 0))
    boston, laker = player(a, 0, 0), player(a, 0, 1)
    boston["team"], laker["team"] = "BOS", "LAL"
    report = LeagueAnalysis(a, None).playoff_schedule()
    mine = {r["name"]: r for r in report["mine"]}
    assert mine[boston["name"]]["games"] == [7, 7, 7] and mine[boston["name"]]["total"] == 21
    assert mine[laker["name"]]["total"] == 3
    assert report["mine"][0]["name"] == boston["name"]
    teams = {r["index"]: r for r in report["teams"]}
    assert teams[0]["player_games"] == 24  # the other six on "XXX" never play
    assert report["teams"][0]["index"] == 0


def test_free_agents_with_full_playoff_weeks_are_listed():
    sunday = date(2027, 4, 11)
    a = build(schedule=season_schedule(sunday, lambda t, d: t == "BOS"))
    free = next(p for p in sorted(a.ranker.players, key=lambda p: -sum(p["z"].values()))
                if p["name"] not in a.snapshot.rostered())
    free["team"] = "BOS"
    report = LeagueAnalysis(a, None).playoff_schedule()
    assert report["free_agents"][0]["name"] == free["name"] and report["free_agents"][0]["total"] == 21


def test_no_playoff_schedule_without_one_or_after_the_season():
    assert LeagueAnalysis(build(), None).playoff_schedule()["available"] is False
    late = build(schedule=season_schedule(date(2027, 4, 11)), today=date(2027, 4, 20))
    assert LeagueAnalysis(late, None).playoff_schedule()["available"] is False


def test_playoff_weeks_already_played_are_left_out():
    a = build(schedule=season_schedule(date(2027, 4, 11)), today=date(2027, 4, 1))
    weeks = LeagueAnalysis(a, None).playoff_schedule()["weeks"]
    assert [w["start"] for w in weeks] == ["2027-03-29", "2027-04-05"]


# ---------- the whole report ----------
def test_the_report_has_every_section():
    report = LeagueAnalysis(build(), None).report()
    assert set(report) == {"power_rankings", "buy_sell", "trade_ideas", "playoffs"}
