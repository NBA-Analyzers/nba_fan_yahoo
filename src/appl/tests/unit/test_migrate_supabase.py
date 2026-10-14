from appl.draft.manual_league import user_hash
from appl.repository.firestore import AuthService, FantasyService, YahooLeagueRepository
from appl.scripts.migrate_supabase_to_firestore import migrate
from appl.tests.unit.fake_firestore import FakeFirestore

TABLES = {
    "google_auth": [{"google_user_id": "g1", "full_name": "Ann", "email": "A@X.com",
                     "access_token": "google-secret", "created_at": "2024-01-01T00:00:00"},
                    {"google_user_id": "", "email": "bad@x.com"}],
    "yahoo_auth": [{"yahoo_user_id": "y1", "access_token": "a", "refresh_token": "r",
                    "username": "bob"}],
    "google_fantasy": [{"google_user_id": "g1", "fantasy_user_id": "y1",
                        "fantasy_platform": "yahoo"}],
    "yahoo_league": [{"league_id": "L1", "yahoo_user_id": "y1", "team_name": "T",
                      "league_name": "N", "team_id": "3", "last_blob_sync": None}],
}


def test_dry_run_writes_nothing_and_counts():
    db = FakeFirestore()
    counts = migrate(TABLES, db, dry_run=True)
    assert db.data == {}
    assert counts["users"]["written"] == 1 and counts["users"]["invalid"] == 1
    assert counts["yahoo_leagues"]["written"] == 1


def test_migrated_data_is_readable_by_the_new_services_and_keeps_the_google_token():
    db = FakeFirestore()
    migrate(TABLES, db, dry_run=False)
    assert AuthService(db).get_google_user("g1").email == "a@x.com"
    assert db.docs("users")[user_hash("g1")]["access_token"] == "google-secret"
    assert AuthService(db).get_yahoo_user("y1").refresh_token == "r"
    assert FantasyService(db).get_yahoo_user_id_for_google_user("g1") == "y1"
    assert YahooLeagueRepository(db).league_exist_for_user("L1", "y1")
    assert YahooLeagueRepository(db).league_exist_for_user("L1", "y2") is None
    assert db.docs("identities")[user_hash("google.com:g1")]["user_id"] == "g1"


def test_rerun_is_idempotent_and_never_overwrites_newer_tokens():
    db = FakeFirestore()
    migrate(TABLES, db, dry_run=False)
    AuthService(db).update_yahoo_tokens("y1", "newer-a", "newer-r")
    before = {k: dict(v) for k, v in db.data.items()}
    counts = migrate(TABLES, db, dry_run=False)
    assert db.data == before
    assert counts["yahoo_auth"]["written"] == 0 and counts["yahoo_auth"]["skipped"] == 1
