"""Users, Yahoo logins, links and leagues in Firestore, against an in-memory fake."""
import pytest

from appl.draft.manual_league import user_hash
from appl.repository.firestore import (AuthService, FantasyService, GoogleAuth, GoogleFantasy,
                                       ValidationError, YahooAuth, YahooLeagueRepository,
                                       retry_once)
from appl.tests.unit.fake_firestore import FakeFirestore


@pytest.fixture
def db():
    return FakeFirestore()


def test_double_login_produces_one_document(db):
    auth = AuthService(db)
    for _ in range(2):
        auth.create_or_update_google_user(GoogleAuth("sub1", "Ann", "A@X.com", "tok"))
    docs = db.docs("users")
    assert list(docs) == [user_hash("sub1")]
    assert docs[user_hash("sub1")]["email"] == "a@x.com"
    assert docs[user_hash("sub1")]["access_token"] == "tok"  # kept, server-side only


def test_yahoo_user_double_write_is_one_document_and_keeps_username(db):
    auth = AuthService(db)
    auth.create_or_update_yahoo_user(YahooAuth("guid1", "a1", "r1", "bob"))
    auth.create_or_update_yahoo_user(YahooAuth("guid1", "a2", "r2"))
    assert list(db.docs("yahoo_auth")) == ["guid1"]
    saved = auth.get_yahoo_user("guid1")
    assert (saved.access_token, saved.refresh_token, saved.username) == ("a2", "r2", "bob")


def test_yahoo_reconnect_is_idempotent_and_does_not_raise(db):
    AuthService(db).create_or_update_yahoo_user(YahooAuth("guid1", "a", "r"))
    fantasy = FantasyService(db)
    link = GoogleFantasy("sub1", "guid1", "yahoo")
    fantasy.connect_fantasy_platform(link)
    fantasy.connect_fantasy_platform(link)
    assert len(db.docs("fantasy_connections")) == 1
    assert fantasy.get_yahoo_user_id_for_google_user("sub1") == "guid1"


def test_connection_needs_the_yahoo_login_to_exist(db):
    with pytest.raises(ValidationError):
        FantasyService(db).connect_fantasy_platform(GoogleFantasy("sub1", "ghost", "yahoo"))


def test_yahoo_lookup_only_returns_links_for_that_user(db):
    AuthService(db).create_or_update_yahoo_user(YahooAuth("guid1", "a", "r"))
    fantasy = FantasyService(db)
    fantasy.connect_fantasy_platform(GoogleFantasy("sub1", "guid1", "yahoo"))
    assert fantasy.get_yahoo_user_id_for_google_user("sub2") is None


def test_league_access_rejects_a_league_the_user_is_not_linked_to(db):
    leagues = YahooLeagueRepository(db)
    leagues.create({"league_id": "L1", "yahoo_user_id": "guid1", "team_name": "T"})
    assert leagues.league_exist_for_user("L1", "guid1")
    assert leagues.league_exist_for_user("L1", "guid2") is None
    assert leagues.league_exist_for_user("L2", "guid1") is None
    assert leagues.league_exist_for_user("L1", "") is None


def test_league_create_then_update_keeps_one_document(db):
    leagues = YahooLeagueRepository(db)
    leagues.create({"league_id": "L1", "yahoo_user_id": "guid1", "team_name": "T"})
    leagues.update_by_league_id_and_yahoo_user_id("L1", "guid1", {"last_blob_sync": "now"})
    assert len(db.docs("yahoo_leagues")) == 1
    assert leagues.get_by_league_id("L1")["last_blob_sync"] == "now"
    assert [x["league_id"] for x in leagues.get_by_yahoo_user_id("guid1")] == ["L1"]


def test_ids_with_slashes_are_rejected(db):
    with pytest.raises(ValidationError):
        YahooLeagueRepository(db).league_exist_for_user("a/b", "guid1")


def test_retry_once_retries_a_transient_error():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("blip")
        return "ok"

    assert retry_once(flaky) == "ok" and len(calls) == 2


def test_retry_once_gives_up_after_the_second_failure():
    def broken():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        retry_once(broken)
