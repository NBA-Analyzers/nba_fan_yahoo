import pytest

from appl.ai.chat_service import ChatService
from appl.ai.litellm_adapters import LLMError
from appl.ai.retrieval import Document, RetrievalService
from appl.service.chat_session_manager import ChatSessionManager


@pytest.fixture
def retrieval(embedder, memory_store):
    r = RetrievalService(embedder, memory_store, top_k=3)
    r.index("general", [Document(source="rules.pdf", text="steals count two points")])
    r.index("league_9", [Document(source="roster.json", text="my roster has Curry")])
    return r


@pytest.fixture
def service(llm, retrieval):
    return ChatService(
        llm=llm,
        retrieval=retrieval,
        sessions=ChatSessionManager(),
        system_prompt="You are a fantasy expert.",
    )


def test_returns_llm_answer(service, llm):
    llm.reply = "Start Curry"
    assert service.chat({"session_id": "s", "user_message": "who?", "league_id": "9"}) == "Start Curry"


def test_system_prompt_is_first_and_user_message_last(service, llm):
    service.chat({"session_id": "s", "user_message": "who?", "league_id": "9"})
    messages = llm.calls[0]
    assert messages[0] == {"role": "system", "content": "You are a fantasy expert."}
    assert messages[-1] == {"role": "user", "content": "who?"}


def test_league_and_general_context_are_injected(service, llm):
    service.chat({"session_id": "s", "user_message": "roster steals", "league_id": "9"})
    context = " ".join(m["content"] for m in llm.calls[0] if m["role"] == "system")
    assert "my roster has Curry" in context
    assert "steals count two points" in context


def test_without_league_only_general_context_is_used(service, llm):
    service.chat({"session_id": "s", "user_message": "roster steals", "league_id": None})
    context = " ".join(m["content"] for m in llm.calls[0] if m["role"] == "system")
    assert "steals count two points" in context
    assert "my roster has Curry" not in context


def test_missing_league_id_key_is_allowed(service, llm):
    service.chat({"session_id": "s", "user_message": "steals"})
    assert len(llm.calls) == 1


def test_history_is_sent_and_reply_is_saved(service, llm):
    llm.reply = "first answer"
    service.chat({"session_id": "s", "user_message": "one"})
    service.chat({"session_id": "s", "user_message": "two"})
    roles_and_text = [(m["role"], m["content"]) for m in llm.calls[1]]
    assert ("user", "one") in roles_and_text
    assert ("assistant", "first answer") in roles_and_text
    assert roles_and_text[-1] == ("user", "two")


def test_sessions_do_not_share_history(service, llm):
    service.chat({"session_id": "a", "user_message": "secret-a"})
    service.chat({"session_id": "b", "user_message": "from b"})
    assert all("secret-a" not in m["content"] for m in llm.calls[1])


def test_llm_failure_propagates_and_history_is_not_polluted(service, llm):
    def boom(messages):
        raise LLMError("down")

    llm.complete = boom
    with pytest.raises(LLMError):
        service.chat({"session_id": "s", "user_message": "hi"})
    assert service.sessions.history("s") == []


@pytest.mark.parametrize("bad", [{}, {"session_id": "s"}, {"user_message": "x"}, {"session_id": "s", "user_message": " "}])
def test_invalid_request_raises_value_error(service, bad):
    with pytest.raises(ValueError):
        service.chat(bad)
