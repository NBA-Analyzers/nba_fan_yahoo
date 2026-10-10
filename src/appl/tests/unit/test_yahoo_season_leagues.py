import pytest

from appl.fantasy_integrations.yahoo.sync_league import yahoo_service as ys
from appl.ingest.season import current_season, yahoo_game_year

THIS_YEAR = yahoo_game_year(current_season())


class FakeGame:
    def __init__(self, ids, fail=False):
        self.ids = ids
        self.fail = fail
        self.calls = []

    def league_ids(self, year=None):
        self.calls.append(year)
        if self.fail:
            raise RuntimeError("Yahoo is down")
        return list(self.ids)


class FakeRepo:
    rows = []

    def get_by_yahoo_user_id(self, yahoo_user_id):
        return [r for r in self.rows if r["yahoo_user_id"] == yahoo_user_id]


@pytest.fixture
def service(monkeypatch):
    ys._season_league_ids.clear()
    game = FakeGame(["466.l.100", "466.l.200"])
    monkeypatch.setattr(ys, "get_yahoo_sdk", lambda token_store, session: game)
    monkeypatch.setattr(ys, "YahooLeagueRepository", FakeRepo)
    FakeRepo.rows = [
        {"yahoo_user_id": "Y1", "league_id": "466.l.100", "league_name": "This season"},
        {"yahoo_user_id": "Y1", "league_id": "454.l.100", "league_name": "Same league, last season"},
        {"yahoo_user_id": "Y1", "league_id": "454.l.999", "league_name": "Old league"},
        {"yahoo_user_id": "Y2", "league_id": "466.l.200", "league_name": "Someone else's"},
    ]
    svc = ys.YahooService({"G1": {"guid": "Y1"}}, document_indexer=None)
    yield svc, game
    ys._season_league_ids.clear()


def test_lists_only_this_seasons_leagues(service):
    svc, game = service
    leagues = svc.get_user_synced_leagues("G1")
    assert [l["league_name"] for l in leagues] == ["This season"]
    assert game.calls == [THIS_YEAR]


def test_season_league_ids_are_cached(service):
    svc, game = service
    svc.get_user_synced_leagues("G1")
    svc.get_user_synced_leagues("G1")
    assert len(game.calls) == 1


def test_no_yahoo_call_when_nothing_synced(service):
    svc, game = service
    FakeRepo.rows = []
    assert svc.get_user_synced_leagues("G1") == []
    assert game.calls == []


def test_yahoo_failure_is_raised_not_hidden(service):
    svc, game = service
    game.fail = True
    with pytest.raises(RuntimeError):
        svc.get_user_synced_leagues("G1")
