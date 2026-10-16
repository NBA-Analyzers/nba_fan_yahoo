from types import SimpleNamespace

import pytest

from appl.draft import service as draft_service
from appl.draft.service import DraftService, StateOptions
from appl.draft.yahoo_draft import YahooDraftTracker
from appl.tests.unit.test_draft import _name, _player
from appl.tests.unit.test_draft_routes import FakeTracker


@pytest.fixture
def pool(monkeypatch):
    players = [_player(_name("Big", i), True, i) for i in range(80)]
    players += [_player(_name("Guard", i), False, 100 + i) for i in range(120)]
    loads = []
    monkeypatch.setattr(draft_service, "load_player_pool", lambda: loads.append(1) or players)
    return loads


def options(**kw):
    base = dict(punts=[], mock=False, auto_punts=False, mode="manual", preference="",
                nominee="", draft_position=None, mock_taken=[], mock_mine=[], mock_costs=None)
    return StateOptions(**{**base, **kw})


def tracker_for(key):
    tracker = FakeTracker()
    tracker.cache_key = key
    return tracker


def test_state_has_recommendations_and_the_roster_profile(pool):
    data = DraftService().state("L1", FakeTracker(), options(punts=["TO"]))
    assert len(data["recommendations"]) == 25 and data["punts"] == ["TO"]
    assert "roster_profile" in data and data["decision"] is None


def test_rankers_are_cached_per_key(pool):
    drafts = DraftService()
    drafts.state("L1", tracker_for("a"), options())
    drafts.state("L1", tracker_for("a"), options())
    assert len(pool) == 1
    drafts.state("L1", tracker_for("b"), options())  # another user of the same league
    assert len(pool) == 2


def test_the_ranker_cache_is_bounded(pool):
    drafts = DraftService(max_rankers=2)
    for key in ("a", "b", "c"):
        drafts.state("L1", tracker_for(key), options())
    assert drafts.cached_rankers == 2
    drafts.state("L1", tracker_for("a"), options())  # "a" was evicted, so it is rebuilt
    assert len(pool) == 4


def test_yahoo_trackers_are_cached_per_user_and_league():
    league = SimpleNamespace(league_id="428.l.1")
    first = YahooDraftTracker(league, user="guid-1")
    second = YahooDraftTracker(league, user="guid-2")
    assert first.cache_key != second.cache_key
    assert "428.l.1" in first.cache_key
