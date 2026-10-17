"""The week a head-to-head matchup is played in, and the stats already scored in it."""

from datetime import date
from types import SimpleNamespace as NS

from appl.season import snapshot as snapshots
from appl.season.snapshot import MatchWeek, espn_live_line, week_around, yahoo_live_line

YAHOO_STATS = {
    "Field Goals Made/Attempted (FGM/FGA)": "123/250",
    "Field Goal Percentage (FG%)": ".492",
    "Free Throws Made/Attempted (FTM/FTA)": "40/50",
    "3-Point Field Goals Made (3PTM)": "21",
    "Points": "410",
    "Rebounds": "150",
    "Assists": "98",
    "Steals": "20",
    "Blocks": "11",
    "Turnovers": "45",
}


# ---------- the week ----------
def test_week_around_is_monday_to_sunday():
    wed = date(2026, 10, 14)
    week = week_around(wed)
    assert (week.start, week.end) == (date(2026, 10, 12), date(2026, 10, 18))
    assert week.live == {} and week.number is None
    assert week_around(date(2026, 10, 18)).start == date(2026, 10, 12)  # Sunday is still that week
    assert week_around(date(2026, 10, 19)).start == date(2026, 10, 19)  # Monday starts the next


# ---------- Yahoo's stat lines ----------
def test_yahoo_live_line_splits_makes_and_attempts():
    line = yahoo_live_line(YAHOO_STATS)
    assert line == {"FGM": 123.0, "FGA": 250.0, "FTM": 40.0, "FTA": 50.0, "FG3M": 21.0, "PTS": 410.0,
                    "REB": 150.0, "AST": 98.0, "STL": 20.0, "BLK": 11.0, "TOV": 45.0}


def test_yahoo_live_line_skips_blank_and_unknown_values():
    line = yahoo_live_line({"Points": "-", "Rebounds": None, "stat_999": "5",
                            "Field Goals Made/Attempted (FGM/FGA)": "n/a", "Assists": "12"})
    assert line == {"AST": 12.0}


def test_yahoo_live_line_is_empty_for_a_week_that_has_not_started():
    assert yahoo_live_line({}) == {}
    assert yahoo_live_line(None) == {}


# ---------- ESPN's category scores ----------
def test_espn_live_line_reads_each_category_score():
    cats = {"PTS": {"score": 410.0, "result": "WIN"}, "REB": {"score": 150.0, "result": "LOSS"},
            "3PM": {"score": 21.0, "result": "TIE"}, "TO": {"score": 45.0, "result": "WIN"},
            "FGM": {"score": 123.0, "result": None}, "FGA": {"score": 250.0, "result": None},
            "FG%": {"score": 0.492, "result": "WIN"}}
    line = espn_live_line(cats)
    assert line == {"PTS": 410.0, "REB": 150.0, "FG3M": 21.0, "TOV": 45.0, "FGM": 123.0, "FGA": 250.0}


def test_espn_live_line_is_empty_without_stats():
    assert espn_live_line(None) == {}
    assert espn_live_line({}) == {}


# ---------- Yahoo snapshot ----------
def _yahoo_matchups(stats_a, stats_b):
    def team(key, name, stats):
        return {"team": [[{"team_key": key}, {"name": name}],
                         {"team_points": {"total": "0"},
                          "team_stats": {"stats": [{"stat": {"stat_id": sid, "value": v}} for sid, v in stats]}}]}

    return {"fantasy_content": {"league": [{}, {"scoreboard": {"0": {"matchups": {
        "count": 1,
        "0": {"matchup": {"week": "3", "0": {"teams": {"0": team("t.1", "Us", stats_a),
                                                           "1": team("t.2", "Them", stats_b)}}}},
    }}}}]}}


class MatchupLeague:
    def __init__(self, stats_a=(("12", "100"), ("15", "40")), stats_b=(("12", "90"),), fail_dates=False):
        self._raw = _yahoo_matchups(stats_a, stats_b)
        self.fail_dates = fail_dates

    def settings(self):
        return {"name": "Y", "scoring_type": "head"}

    def teams(self):
        return {"t.1": {"name": "Us", "is_owned_by_current_login": "1"}, "t.2": {"name": "Them"}}

    def to_team(self, key):
        return NS(roster=lambda: [{"name": f"P{key}"}])

    def free_agents(self, pos):
        return []

    def stat_categories(self):
        return [{"display_name": "PTS"}]

    def positions(self):
        return {"Util": {"count": 1}}

    def team_key(self):
        return "t.1"

    def current_week(self):
        return 3

    def matchups(self, week=None):
        return self._raw

    def week_date_range(self, week):
        if self.fail_dates:
            raise RuntimeError("no dates")
        return date(2026, 10, 12), date(2026, 10, 18)


def test_yahoo_snapshot_carries_the_week_and_both_teams_live_stats():
    snapshots._yahoo_cache.clear()
    snap = snapshots.from_yahoo(MatchupLeague(), "wk-1", user="u")
    assert snap.opponent == 1
    week = snap.week
    assert (week.number, week.start, week.end) == (3, date(2026, 10, 12), date(2026, 10, 18))
    assert week.live == {0: {"PTS": 100.0, "REB": 40.0}, 1: {"PTS": 90.0}}


def test_yahoo_snapshot_falls_back_to_the_calendar_week_when_dates_fail():
    snapshots._yahoo_cache.clear()
    snap = snapshots.from_yahoo(MatchupLeague(fail_dates=True), "wk-2", user="u")
    assert snap.week.number == 3
    assert snap.week.start.weekday() == 0 and (snap.week.end - snap.week.start).days == 6


def test_yahoo_snapshot_has_no_week_when_there_is_no_matchup():
    class NoMatchup(MatchupLeague):
        def matchups(self, week=None):
            raise RuntimeError("offseason")

    snapshots._yahoo_cache.clear()
    snap = snapshots.from_yahoo(NoMatchup(), "wk-3", user="u")
    assert snap.opponent is None and snap.week is None


# ---------- ESPN snapshot ----------
def test_espn_snapshot_carries_the_week_and_live_stats():
    from appl.tests.unit.test_espn import SWID, rich_league

    league = rich_league()

    def scoreboard(week):
        a, b = league.teams
        return [NS(home_team=a, away_team=b, home_final_score=0, away_final_score=0, winner="UNDECIDED",
                   home_team_cats={"PTS": {"score": 300.0, "result": "WIN"}},
                   away_team_cats={"PTS": {"score": 250.0, "result": "LOSS"}})]

    league.scoreboard = scoreboard
    snapshots._espn_cache.clear()
    snap = snapshots.from_espn(league, "wk-e1", swid=SWID, user="u1")
    assert snap.opponent == 1
    assert snap.week.number == 2
    assert snap.week.live == {0: {"PTS": 300.0}, 1: {"PTS": 250.0}}
    assert snap.week.start.weekday() == 0


def test_manual_snapshot_has_a_calendar_week_and_no_live_stats(tmp_path):
    from appl.draft.manual_league import ManualLeagueStore

    store = ManualLeagueStore(tmp_path)
    league = store.create("u", {"name": "Friends", "num_teams": 4, "roster_size": 3, "my_slot": 1})
    snap = snapshots.from_manual(store.get("u", league["id"]))
    assert snap.week.live == {} and snap.week.number is None
    assert snap.week.start.weekday() == 0
    assert (snap.week.end - snap.week.start).days == 6


# ---------- finished weeks (for the luck index) ----------
def test_yahoo_snapshot_reads_each_finished_week_once():
    calls = []

    class Counting(MatchupLeague):
        def matchups(self, week=None):
            calls.append(week)
            return super().matchups(week)

    snapshots._yahoo_cache.clear()
    snapshots._week_cache.clear()
    snap = snapshots.from_yahoo(Counting(), "wk-h1", user="u")
    calls.clear()  # building the snapshot reads this week's matchup; history waits until asked
    weeks = snap.history()
    assert [w.number for w in weeks] == [1, 2]  # week 3 is still being played
    assert weeks[0].pairs == [(0, 1)] and weeks[0].lines == {0: {"PTS": 100.0, "REB": 40.0}, 1: {"PTS": 90.0}}
    snap.history()
    assert calls == [1, 2]  # finished weeks are kept


def test_a_week_that_fails_is_skipped_and_tried_again():
    attempts = {"n": 0}

    def read(number):
        attempts["n"] += 1
        if number == 1 and attempts["n"] == 1:
            raise RuntimeError("timeout")
        return snapshots.PastWeek(number, {0: {"PTS": 1.0}, 1: {"PTS": 2.0}}, [(0, 1)])

    snapshots._week_cache.clear()
    load = snapshots.past_weeks("k", 3, read)
    assert [w.number for w in load()] == [2]
    assert [w.number for w in load()] == [1, 2]


def test_no_history_before_the_first_week_is_over():
    snapshots._week_cache.clear()
    assert snapshots.past_weeks("k", 1, lambda n: None)() == []
    assert snapshots.past_weeks("k", None, lambda n: None)() == []


def test_espn_snapshot_reads_finished_weeks_and_skips_byes():
    from appl.tests.unit.test_espn import SWID, rich_league

    league = rich_league()
    a, b = league.teams

    def scoreboard(week):
        return [NS(home_team=a, away_team=b, home_team_cats={"PTS": {"score": 300.0 + week}},
                   away_team_cats={"PTS": {"score": 250.0}}),
                NS(home_team=a, away_team=0, home_team_cats={}, away_team_cats={})]  # a bye

    league.scoreboard = scoreboard
    snapshots._espn_cache.clear()
    snapshots._week_cache.clear()
    snap = snapshots.from_espn(league, "wk-h2", swid=SWID, user="u1")
    weeks = snap.history()
    assert [w.number for w in weeks] == [1]  # the current period is 2
    assert weeks[0].pairs == [(0, 1)] and weeks[0].lines == {0: {"PTS": 301.0}, 1: {"PTS": 250.0}}


def test_manual_snapshots_have_no_history(tmp_path):
    from appl.draft.manual_league import ManualLeagueStore

    store = ManualLeagueStore(tmp_path)
    league = store.create("u", {"name": "Friends", "num_teams": 4, "roster_size": 3, "my_slot": 1})
    assert snapshots.from_manual(store.get("u", league["id"])).history is None
