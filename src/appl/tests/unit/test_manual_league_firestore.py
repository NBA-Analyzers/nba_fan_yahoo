"""Manual leagues on Firestore. Logic runs against a fake client (offline); the same
behaviour is checked on both backends. A real-Firestore round trip runs when
FIRESTORE_TEST_PROJECT is set (pytest -m integration)."""
import copy
import os
import uuid

import pytest

from appl.draft import manual_league
from appl.draft.manual_league import (
    FileBackend,
    FirestoreBackend,
    ManualLeagueError,
    ManualLeagueStore,
    default_store,
    user_hash,
)


# ---------- minimal fake of the Firestore client surface we use ----------
class FakeSnap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeDocRef:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return FakeCollRef(self.db, f"{self.path}/{name}")

    def set(self, data):
        self.db.data[self.path] = copy.deepcopy(data)

    def get(self, transaction=None):
        return FakeSnap(self.db.data.get(self.path))

    def delete(self):
        self.db.data.pop(self.path, None)


class FakeCollRef:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id):
        return FakeDocRef(self.db, f"{self.path}/{doc_id}")

    def stream(self):
        prefix = self.path + "/"
        return [
            FakeSnap(data) for path, data in sorted(self.db.data.items())
            if path.startswith(prefix) and "/" not in path[len(prefix):]
        ]


class FakeTransaction:
    """Writes are buffered and applied only if the transaction body finishes."""

    def __init__(self):
        self.writes = []

    def set(self, ref, data):
        self.writes.append((ref, data))

    def commit(self):
        for ref, data in self.writes:
            ref.set(data)


class FakeClient:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return FakeCollRef(self, name)

    def transaction(self):
        return FakeTransaction()


def fake_transactional(fn):
    def run(transaction):
        result = fn(transaction)  # an exception here means no commit
        transaction.commit()
        return result

    return run


# ---------- the same tests on both backends ----------
@pytest.fixture(params=["file", "firestore"])
def make_store(request, tmp_path):
    """Builds stores that share one storage, so a second store acts like a restart."""
    client = FakeClient()

    def build():
        if request.param == "file":
            return ManualLeagueStore(tmp_path)
        return ManualLeagueStore(backend=FirestoreBackend(client, transactional=fake_transactional))

    build.client = client
    build.kind = request.param
    return build


SETTINGS = {"name": "Friends", "num_teams": 4, "roster_size": 3}


def test_create_list_get_delete(make_store):
    store = make_store()
    league = store.create("alice", SETTINGS)
    assert [l["id"] for l in store.list("alice")] == [league["id"]]
    assert store.get("alice", league["id"])["name"] == "Friends"
    store.delete("alice", league["id"])
    assert store.list("alice") == []
    with pytest.raises(KeyError):
        store.get("alice", league["id"])


def test_picks_undo_and_notes_are_saved(make_store):
    store, league = make_store(), None
    league = store.create("alice", SETTINGS)
    store.add_pick("alice", league["id"], "Nikola Jokic")
    store.add_pick("alice", league["id"], "Luka Doncic")
    store.undo_pick("alice", league["id"])
    store.add_note("alice", league["id"], "Watch his minutes")
    saved = store.get("alice", league["id"])
    assert [p["player_name"] for p in saved["picks"]] == ["Nikola Jokic"]
    assert saved["notes"][0]["text"] == "Watch his minutes"
    assert saved["notes"][0]["phase"] == "during"


def test_a_failed_change_saves_nothing(make_store):
    store = make_store()
    league = store.create("alice", SETTINGS)
    store.add_pick("alice", league["id"], "Nikola Jokic")
    with pytest.raises(ManualLeagueError):
        store.add_pick("alice", league["id"], "nikola jokic")  # already picked
    assert len(store.get("alice", league["id"])["picks"]) == 1


def test_leagues_survive_a_restart(make_store):
    league = make_store().create("alice", SETTINGS)
    restarted = make_store()
    assert restarted.get("alice", league["id"])["name"] == "Friends"
    assert [l["id"] for l in restarted.list("alice")] == [league["id"]]


def test_users_cannot_see_each_others_leagues(make_store):
    store = make_store()
    league = store.create("alice", SETTINGS)
    assert store.list("bob") == []
    with pytest.raises(KeyError):
        store.get("bob", league["id"])
    with pytest.raises(KeyError):
        store.add_pick("bob", league["id"], "Nikola Jokic")


def test_bad_ids_are_unknown_leagues(make_store):
    store = make_store()
    for bad in ("", "../etc/passwd", "x" * 12, "A" * 12):
        with pytest.raises(KeyError):
            store.get("alice", bad)
        with pytest.raises(KeyError):
            store.delete("alice", bad)


# ---------- Firestore specifics ----------
def test_firestore_layout_keeps_raw_user_ids_out_of_paths():
    client = FakeClient()
    store = ManualLeagueStore(backend=FirestoreBackend(client, transactional=fake_transactional))
    league = store.create("alice@example.com", SETTINGS)
    assert list(client.data) == [f"manual_leagues/{user_hash('alice@example.com')}/leagues/{league['id']}"]
    assert "alice" not in next(iter(client.data))


def test_modify_on_a_missing_league_raises_key_error():
    store = ManualLeagueStore(backend=FirestoreBackend(FakeClient(), transactional=fake_transactional))
    with pytest.raises(KeyError):
        store.add_note("alice", "0123456789ab", "hello")


def test_building_the_backend_needs_no_credentials():
    backend = FirestoreBackend()  # no client created until first use
    assert backend._client_obj is None


def test_default_store_picks_firestore_on_cloud_run_and_files_elsewhere(monkeypatch):
    monkeypatch.delenv("MANUAL_LEAGUE_STORE", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert isinstance(default_store().backend, FileBackend)
    monkeypatch.setenv("K_SERVICE", "fantasy-ai")  # set automatically by Cloud Run
    assert isinstance(default_store().backend, FirestoreBackend)
    monkeypatch.setenv("MANUAL_LEAGUE_STORE", "file")
    assert isinstance(default_store().backend, FileBackend)
    monkeypatch.setenv("MANUAL_LEAGUE_STORE", "firestore")
    monkeypatch.delenv("K_SERVICE")
    assert isinstance(default_store().backend, FirestoreBackend)


# ---------- real Firestore (pytest -m integration) ----------
@pytest.mark.integration
def test_real_firestore_round_trip():
    project = os.environ.get("FIRESTORE_TEST_PROJECT")
    if not project:
        pytest.skip("set FIRESTORE_TEST_PROJECT to run against a real Firestore")
    from google.cloud import firestore

    client = firestore.Client(project=project)
    root = f"manual_leagues_test_{uuid.uuid4().hex[:8]}"
    store = ManualLeagueStore(backend=FirestoreBackend(client, root=root))
    user = f"user-{uuid.uuid4().hex[:6]}"
    league = store.create(user, SETTINGS)
    try:
        store.add_pick(user, league["id"], "Nikola Jokic")
        store.add_note(user, league["id"], "real transaction")
        with pytest.raises(ManualLeagueError):
            store.add_pick(user, league["id"], "Nikola Jokic")
        saved = store.get(user, league["id"])
        assert len(saved["picks"]) == 1 and saved["notes"][0]["text"] == "real transaction"
        assert [l["id"] for l in store.list(user)] == [league["id"]]
    finally:
        store.delete(user, league["id"])
        client.collection(root).document(user_hash(user)).delete()
