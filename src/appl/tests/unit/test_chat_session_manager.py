from appl.service.chat_session_manager import ChatSessionManager


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
    def __init__(self):
        self.data, self.saves, self.fail_loads = {}, 0, False

    def load(self, session_id):
        if self.fail_loads:
            raise TimeoutError("firestore timeout")
        return [dict(m) for m in self.data[session_id]] if session_id in self.data else None

    def save(self, session_id, messages):
        self.saves += 1
        self.data[session_id] = [dict(m) for m in messages]


def test_a_failed_load_never_overwrites_the_stored_conversation():
    store = FlakyStore()
    store.data["s1"] = [{"role": "user", "content": f"old{i}"} for i in range(4)]
    m = ChatSessionManager(store)
    store.fail_loads = True
    m.add_message("s1", "user", "new")
    assert [x["content"] for x in store.data["s1"]] == ["old0", "old1", "old2", "old3"]


def test_instances_sharing_a_store_see_and_keep_each_others_messages():
    store = FlakyStore()
    a, b = ChatSessionManager(store), ChatSessionManager(store)
    a.add_messages("s1", [("user", "q1"), ("assistant", "a1")])
    assert [x["content"] for x in b.history("s1")] == ["q1", "a1"]
    b.add_messages("s1", [("user", "q2"), ("assistant", "a2")])
    assert [x["content"] for x in a.history("s1")] == ["q1", "a1", "q2", "a2"]
    a.add_messages("s1", [("user", "q3"), ("assistant", "a3")])
    assert [x["content"] for x in store.data["s1"]] == ["q1", "a1", "q2", "a2", "q3", "a3"]


def test_a_turn_is_saved_in_one_write():
    store = FlakyStore()
    ChatSessionManager(store).add_messages("s1", [("user", "q"), ("assistant", "a")])
    assert store.saves == 1


def test_history_falls_back_to_memory_when_the_store_cant_be_read():
    store = FlakyStore()
    m = ChatSessionManager(store)
    m.add_message("s1", "user", "hi")
    store.fail_loads = True
    assert [x["content"] for x in m.history("s1")] == ["hi"]
