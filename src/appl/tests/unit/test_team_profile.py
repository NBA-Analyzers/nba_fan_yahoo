"""Your team in depth: profile, player contributions, the league grid and scouting."""

import pytest

from appl.season.analyzer import SeasonAnalyzer
from appl.season.team_profile import DRAG_Z, TeamProfile
from appl.tests.unit.test_matchup_planner import SLOTS, WED, build
from appl.tests.unit.test_season import _snapshot_league


@pytest.fixture
def league():
    ranker, snap = _snapshot_league()
    analyzer = SeasonAnalyzer(ranker, snap)
    return TeamProfile(analyzer), analyzer


# ---------- profile ----------
def test_profile_has_a_row_per_category_with_rank_and_label(league):
    profile, analyzer = league
    rows = profile.profile()
    assert [r["category"] for r in rows] == analyzer.categories
    mine = {r["category"]: r for r in analyzer.my_categories()}
    for r in rows:
        assert r["rank"] == mine[r["category"]]["rank"] and r["label"] == mine[r["category"]]["label"]


def test_profile_z_is_positive_when_better_than_the_league_average(league):
    profile, analyzer = league
    rows = profile.profile()
    best = [r for r in rows if r["rank"] == 1]
    worst = [r for r in rows if r["rank"] == analyzer.snapshot.num_teams]
    assert all(r["z"] > 0 for r in best) and all(r["z"] < 0 for r in worst)
    assert all(r["z"] > 0 for r in rows if r["label"] == "strong")


def test_turnover_z_is_flipped_so_fewer_is_better(league):
    profile, analyzer = league
    values = analyzer._values["TO"]
    row = next(r for r in profile.profile() if r["category"] == "TO")
    fewer_than_average = values[analyzer.me] < sum(values) / len(values)
    assert (row["z"] > 0) == fewer_than_average and row["z"] != 0


def test_punted_categories_are_marked():
    _, analyzer, _ = build(punts=["BLK"])
    rows = {r["category"]: r for r in TeamProfile(analyzer).profile()}
    assert rows["BLK"]["punted"] and not rows["PTS"]["punted"]


# ---------- contributions ----------
def test_contributions_rank_players_and_flag_the_drags():
    _, analyzer, _ = build(hurt_mine=2)
    data = TeamProfile(analyzer).contributions()
    players = data["players"]
    assert [p["value"] for p in players] == sorted((p["value"] for p in players), reverse=True)
    weak = players[-1]
    assert weak["name"].startswith("Alpha") and weak["drags"]
    assert all(weak["z"][c] <= DRAG_Z for c in weak["drags"])
    assert weak["value"] == min(p["value"] for p in players) and weak["value"] < 0


def test_a_category_is_carried_by_the_best_player_in_it():
    _, analyzer, _ = build()
    data = TeamProfile(analyzer).contributions()
    for c, names in data["carriers"].items():
        best = max(data["players"], key=lambda p: p["z"][c])
        assert names == ([best["name"]] if best["z"][c] > 0 else [])


def test_games_this_week_and_next_come_from_the_schedule():
    _, analyzer, _ = build(slots=SLOTS)
    assert analyzer.today == WED
    lal = next(p for p in TeamProfile(analyzer).contributions()["players"] if p["team"] == "LAL")
    assert lal["games_this_week"] == 4  # Wed, Thu, Fri and Sunday
    assert lal["games_next_week"] is None  # the schedule file has nothing for next week


def test_games_are_unknown_without_a_schedule():
    from appl.season.schedule import Schedule

    _, analyzer, _ = build(sched=Schedule({}))
    player = TeamProfile(analyzer).contributions()["players"][0]
    assert player["games_this_week"] is None


def test_injuries_and_form_are_attached_to_players():
    class Data:
        def form(self, name):
            return {"minutes_trend": 4.5} if name.startswith("Alpha") else None

        def risers(self, names):
            return [{"name": names[0], "minutes_trend": 4.5}]

    _, analyzer, _ = build(injuries={"Alpha Ae": "out"})
    data = TeamProfile(analyzer, Data()).contributions()
    assert any(p["injury"] == "out" for p in data["players"])
    assert all(p["minutes_trend"] == 4.5 for p in data["players"])
    assert data["risers"][0]["minutes_trend"] == 4.5
    assert TeamProfile(analyzer).contributions()["risers"] == []  # no data, no form


# ---------- league grid ----------
def test_the_grid_has_every_other_team_hardest_first(league):
    profile, analyzer = league
    grid = profile.league_grid()
    assert len(grid) == analyzer.snapshot.num_teams - 1
    assert analyzer.me not in [g["index"] for g in grid]
    wins = [g["expected_wins"] for g in grid]
    assert wins == sorted(wins)
    for g in grid:
        assert set(g["categories"]) == set(analyzer.counted)
        assert all(0.0 <= p <= 1.0 for p in g["categories"].values())
        r = g["record"]
        assert r["wins"] + r["losses"] + r["ties"] == len(analyzer.counted)
        assert g["expected_wins"] == pytest.approx(sum(g["categories"].values()), abs=0.02)


def test_the_grid_is_symmetric_between_two_teams(league):
    profile, analyzer = league
    a, b = analyzer.me, (analyzer.me + 1) % profile.n
    for c in analyzer.counted:
        forward = analyzer._beat_prob(c, analyzer._values[c][a], analyzer._values[c][b])
        back = analyzer._beat_prob(c, analyzer._values[c][b], analyzer._values[c][a])
        assert forward + back == pytest.approx(1.0)


def test_twins_are_a_coin_flip_in_every_category():
    grid = TeamProfile(build()[1]).league_grid()
    twin = next(g for g in grid if g["index"] == 1)
    assert all(p == 0.5 for p in twin["categories"].values())
    assert twin["swing"] == list(twin["categories"]) and twin["record"]["ties"] == len(twin["categories"])


def test_punts_leave_the_grid():
    _, analyzer, _ = build(punts=["BLK"])
    grid = TeamProfile(analyzer).league_grid()
    assert all("BLK" not in g["categories"] for g in grid)


# ---------- scouting ----------
def test_scouting_cards_name_strengths_weaknesses_and_trade_fit(league):
    profile, analyzer = league
    cards = profile.scouting()
    assert len(cards) == analyzer.snapshot.num_teams - 1
    for card in cards:
        t = card["index"]
        assert set(card["ranks"]) == set(analyzer.categories)
        assert set(card["strengths"]).isdisjoint(card["weaknesses"])
        # What I can offer: they are weak and I am strong there. The reverse for what I need.
        for c in card["you_offer"]:
            assert profile._label(t, c) == "weak" and profile._label(analyzer.me, c) == "strong"
        for c in card["you_need"]:
            assert profile._label(t, c) == "strong" and profile._label(analyzer.me, c) == "weak"
        assert len(card["top_players"]) == 3


def test_scouting_lists_the_rivals_injuries():
    _, analyzer, _ = build(injuries={"Bravo Ab": "out", "Bravo Ae": "questionable"})
    card = next(c for c in TeamProfile(analyzer).scouting() if c["index"] == 1)
    assert {(i["name"], i["status"]) for i in card["injuries"]} == {("Bravo Ab", "out"), ("Bravo Ae", "questionable")}


def test_the_report_has_every_section(league):
    profile, _ = league
    assert set(profile.report()) == {"profile", "contributions", "grid", "scouting"}
