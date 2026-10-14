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
