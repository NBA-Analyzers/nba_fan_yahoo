import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from appl.service.chat_session_manager import (
    MAX_STORED_MESSAGES,
    SESSION_DAYS,
    ChatSessionManager,
    FirestoreChatSessionStore,
)
from appl.tests.unit.test_manual_league_firestore import FakeClient, fake_transactional

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def test_new_session_has_empty_history():
    assert ChatSessionManager().history("s1") == []


def test_messages_are_appended_in_order():
    m = ChatSessionManager()
    m.add_message("s1", "user", "hi")
    m.add_message("s1", "assistant", "hello")
    assert m.history("s1") == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_history_is_capped_to_last_n_turns():
    m = ChatSessionManager()
    for i in range(5):
        m.add_message("s1", "user", f"q{i}")
        m.add_message("s1", "assistant", f"a{i}")
    history = m.history("s1", max_turns=2)
    assert [h["content"] for h in history] == ["q3", "a3", "q4", "a4"]


def test_sessions_are_isolated():
    m = ChatSessionManager()
    m.add_message("s1", "user", "one")
    m.add_message("s2", "user", "two")
    assert [h["content"] for h in m.history("s1")] == ["one"]


def test_history_returns_a_copy():
    m = ChatSessionManager()
    m.add_message("s1", "user", "hi")
    m.history("s1").append({"role": "user", "content": "tamper"})
    assert len(m.history("s1")) == 1


# ---------- with a shared store (Cloud Run: many instances, one Firestore) ----------
class FlakyStore:
    """Appends are atomic, like the Firestore store's transaction."""

    def __init__(self):
        self.data, self.writes, self.fail_loads = {}, 0, False

    def load(self, session_id):
        if self.fail_loads:
            raise TimeoutError("firestore timeout")
        return [dict(m) for m in self.data[session_id]] if session_id in self.data else None

    def append(self, session_id, messages):
        self.writes += 1
        self.data.setdefault(session_id, []).extend(dict(m) for m in messages)


def test_a_failed_load_never_loses_the_stored_conversation():
    store = FlakyStore()
    store.data["s1"] = [{"role": "user", "content": f"old{i}"} for i in range(4)]
    m = ChatSessionManager(store)
    store.fail_loads = True
    m.add_message("s1", "user", "new")
    assert [x["content"] for x in store.data["s1"]] == ["old0", "old1", "old2", "old3", "new"]


def test_instances_sharing_a_store_see_and_keep_each_others_messages():
    store = FlakyStore()
    a, b = ChatSessionManager(store), ChatSessionManager(store)
    a.add_messages("s1", [("user", "q1"), ("assistant", "a1")])
    assert [x["content"] for x in b.history("s1")] == ["q1", "a1"]
    b.add_messages("s1", [("user", "q2"), ("assistant", "a2")])
    assert [x["content"] for x in a.history("s1")] == ["q1", "a1", "q2", "a2"]
    a.add_messages("s1", [("user", "q3"), ("assistant", "a3")])
    assert [x["content"] for x in store.data["s1"]] == ["q1", "a1", "q2", "a2", "q3", "a3"]


def test_turns_answered_at_the_same_time_are_both_kept():
    """Both instances read the history before either saves; neither save may drop the other."""
    store = FlakyStore()
    a, b = ChatSessionManager(store), ChatSessionManager(store)
    a.add_messages("s1", [("user", "q1"), ("assistant", "a1")])
    a.history("s1"), b.history("s1")
    a.add_messages("s1", [("user", "qa"), ("assistant", "aa")])
    b.add_messages("s1", [("user", "qb"), ("assistant", "ab")])
    assert [x["content"] for x in store.data["s1"]] == ["q1", "a1", "qa", "aa", "qb", "ab"]


def test_a_turn_is_saved_in_one_write():
    store = FlakyStore()
    ChatSessionManager(store).add_messages("s1", [("user", "q"), ("assistant", "a")])
    assert store.writes == 1


def test_history_falls_back_to_memory_when_the_store_cant_be_read():
    store = FlakyStore()
    m = ChatSessionManager(store)
    m.add_message("s1", "user", "hi")
    store.fail_loads = True
    assert [x["content"] for x in m.history("s1")] == ["hi"]


# ---------- the Firestore store (fake client offline, real one with -m integration) ----------
def firestore_store(client, transactional=fake_transactional, **kw):
    return FirestoreChatSessionStore(client, transactional=transactional, now=lambda: NOW, **kw)


def msgs(*texts):
    return [{"role": "user", "content": t} for t in texts]


def test_firestore_appends_in_a_transaction_and_keeps_the_latest_messages():
    client = FakeClient()
    store = firestore_store(client)
    assert store.load("s1") is None
    store.append("s1", msgs("a", "b"))
    store.append("s1", msgs(*(f"m{i}" for i in range(MAX_STORED_MESSAGES))))
    saved = store.load("s1")
    assert len(saved) == MAX_STORED_MESSAGES and saved[-1]["content"] == f"m{MAX_STORED_MESSAGES - 1}"
    (doc,) = client.data.values()
    assert doc["expires_at"] == NOW + timedelta(days=SESSION_DAYS)


def test_firestore_append_survives_a_retry_after_a_conflicting_write():
    """Firestore re-runs a transaction whose document changed under it; the re-run must
    build on the newer messages, not on what the first attempt read."""
    client = FakeClient()
    store = firestore_store(client)
    store.append("s1", msgs("q1"))
    other = firestore_store(client)

    def contended(fn):
        def run(transaction):
            fn(transaction)  # first attempt reads, then another instance commits first
            other.append("s1", msgs("from another instance"))
            retry = client.transaction()
            result = fn(retry)
            retry.commit()
            return result
        return run

    firestore_store(client, transactional=contended).append("s1", msgs("mine"))
    assert [m["content"] for m in store.load("s1")] == ["q1", "from another instance", "mine"]


@pytest.mark.integration
def test_real_firestore_keeps_every_concurrent_append():
    project = os.environ.get("FIRESTORE_TEST_PROJECT")
    if not project:
        pytest.skip("set FIRESTORE_TEST_PROJECT to run against a real Firestore")
    from google.cloud import firestore

    client = firestore.Client(project=project)
    collection = f"chat_sessions_test_{uuid.uuid4().hex[:8]}"
    store = FirestoreChatSessionStore(client, collection=collection)
    session = f"s-{uuid.uuid4().hex[:6]}"
    threads = [threading.Thread(target=store.append, args=(session, msgs(f"t{i}"))) for i in range(5)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert sorted(m["content"] for m in store.load(session)) == [f"t{i}" for i in range(5)]
    finally:
        client.collection(collection).document(store._doc_id(session)).delete()
