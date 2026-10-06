"""FirestoreVectorStore: logic tested against a fake client (offline), and the shared
contract suite against a real Firestore project when FIRESTORE_TEST_PROJECT is set
(run with: pytest -m integration)."""
import os
import uuid

import pytest
from google.cloud.firestore_v1.vector import Vector

from appl.ai.chunker import Chunk
from appl.ai.firestore_store import FirestoreVectorStore
from appl.ai.ports import VectorRecord
from appl.tests.unit.vector_store_contract import VectorStoreContract


# ---------- minimal fake of the Firestore client surface we use ----------
class FakeSnap:
    def __init__(self, ref, data):
        self.reference, self._data = ref, data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return FakeCollRef(self.db, f"{self.path}/{name}")

    def set(self, data):
        self.db.data[self.path] = dict(data)

    def get(self):
        return FakeSnap(self, self.db.data.get(self.path))


class FakeCollRef:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id=None):
        doc_id = doc_id or uuid.uuid4().hex
        return FakeDocRef(self.db, f"{self.path}/{doc_id}")

    def _children(self):
        prefix = self.path + "/"
        return [
            p for p in self.db.data if p.startswith(prefix) and "/" not in p[len(prefix):]
        ]

    def stream(self):
        return [FakeSnap(FakeDocRef(self.db, p), self.db.data[p]) for p in self._children()]

    def find_nearest(self, vector_field, query_vector, limit, distance_measure, *, distance_result_field):
        self.db.nearest_calls.append(
            {"limit": limit, "measure": distance_measure, "field": vector_field}
        )
        rows = []
        for p in self._children():
            d = dict(self.db.data[p])
            d[distance_result_field] = self.db.distances[d["text"]]
            rows.append((d[distance_result_field], FakeSnap(FakeDocRef(self.db, p), d)))
        rows.sort(key=lambda r: r[0])
        outer = [s for _, s in rows[:limit]]

        class Q:
            def stream(_self):
                return outer

        return Q()


class FakeBatch:
    def __init__(self, db):
        self.db, self.ops = db, []

    def set(self, ref, data):
        self.ops.append(("set", ref, data))

    def delete(self, ref):
        self.ops.append(("delete", ref, None))

    def commit(self):
        self.db.batch_sizes.append(len(self.ops))
        for op, ref, data in self.ops:
            if op == "set":
                self.db.data[ref.path] = dict(data)
            else:
                self.db.data.pop(ref.path, None)


class FakeFirestore:
    def __init__(self):
        self.data, self.batch_sizes, self.nearest_calls = {}, [], []
        self.distances = {}  # text -> cosine distance returned by "server"

    def collection(self, name):
        return FakeCollRef(self, name)

    def batch(self):
        return FakeBatch(self)


def _rec(text, i=0):
    return VectorRecord(Chunk(text=text, source="s.pdf", index=i), [1.0, 0.0])


@pytest.fixture
def db():
    return FakeFirestore()


@pytest.fixture
def fs_store(db):
    return FirestoreVectorStore(db, root="rag", batch_size=3)


def test_replace_writes_chunks_as_vectors_with_metadata(fs_store, db):
    fs_store.replace_collection("general", [_rec("hello", 4)])
    stored = [v for p, v in db.data.items() if p.startswith("rag/general/chunks/")]
    assert len(stored) == 1
    assert (stored[0]["text"], stored[0]["source"], stored[0]["index"]) == ("hello", "s.pdf", 4)
    assert isinstance(stored[0]["embedding"], Vector)


def test_replace_removes_previous_chunks_first(fs_store, db):
    fs_store.replace_collection("general", [_rec("old1"), _rec("old2")])
    fs_store.replace_collection("general", [_rec("new")])
    texts = [v["text"] for p, v in db.data.items() if "/chunks/" in p]
    assert texts == ["new"]


def test_writes_are_batched(fs_store, db):
    fs_store.replace_collection("c", [_rec(f"t{i}", i) for i in range(7)])
    assert all(size <= 3 for size in db.batch_sizes)
    assert sum(db.batch_sizes) == 7


def test_last_synced_is_stored_on_the_collection_doc(fs_store):
    assert fs_store.last_synced("general") is None
    fs_store.replace_collection("general", [_rec("x")])
    assert fs_store.last_synced("general") is not None


def test_search_converts_cosine_distance_to_score_and_merges_collections(fs_store, db):
    fs_store.replace_collection("a", [_rec("a-near"), _rec("a-far")])
    fs_store.replace_collection("b", [_rec("b-mid")])
    db.distances = {"a-near": 0.1, "a-far": 0.9, "b-mid": 0.4}

    results = fs_store.search(["a", "b"], [1.0, 0.0], k=2)

    assert [r.chunk.text for r in results] == ["a-near", "b-mid"]
    assert results[0].score == pytest.approx(0.9)
    assert [r.collection_id for r in results] == ["a", "b"]
    assert all(call["limit"] == 2 for call in db.nearest_calls)


# ---------- real Firestore, shared contract ----------
@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("FIRESTORE_TEST_PROJECT"),
    reason="set FIRESTORE_TEST_PROJECT (+ Google credentials) to run",
)
class TestRealFirestore(VectorStoreContract):
    @pytest.fixture
    def store(self):
        from google.cloud import firestore

        client = firestore.Client(project=os.environ["FIRESTORE_TEST_PROJECT"])
        root = f"test_rag_{uuid.uuid4().hex[:8]}"
        store = FirestoreVectorStore(client, root=root)
        yield store
        for coll in client.collection(root).stream():
            for chunk in coll.reference.collection("chunks").stream():
                chunk.reference.delete()
            coll.reference.delete()
