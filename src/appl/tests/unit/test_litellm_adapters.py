from types import SimpleNamespace

import litellm
import pytest

from appl.ai.litellm_adapters import LiteLLMClient, LiteLLMEmbedder, LLMError


def _completion_response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_client_sends_model_and_messages_and_returns_text(monkeypatch):
    seen = {}

    def fake_completion(**kwargs):
        seen.update(kwargs)
        return _completion_response("hi there")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    messages = [{"role": "user", "content": "hello"}]

    assert LiteLLMClient(model="gemini/test-model").complete(messages) == "hi there"
    assert seen["model"] == "gemini/test-model"
    assert seen["messages"] == messages


def test_client_wraps_provider_errors(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("quota")

    monkeypatch.setattr(litellm, "completion", boom)
    with pytest.raises(LLMError, match="quota"):
        LiteLLMClient(model="m").complete([{"role": "user", "content": "x"}])


def test_client_rejects_empty_answer(monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **kw: _completion_response(None))
    with pytest.raises(LLMError):
        LiteLLMClient(model="m").complete([{"role": "user", "content": "x"}])


def test_client_from_env_uses_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert LiteLLMClient.from_env().model == "gemini/gemini-3.8-flash"
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    assert LiteLLMClient.from_env().model == "openai/gpt-4o-mini"


def test_embedder_returns_vectors_in_order(monkeypatch):
    def fake_embedding(**kwargs):
        return SimpleNamespace(
            data=[{"embedding": [float(len(t))]} for t in kwargs["input"]]
        )

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    assert LiteLLMEmbedder(model="e").embed(["a", "bbb"]) == [[1.0], [3.0]]


def test_embedder_batches_large_inputs_and_keeps_order(monkeypatch):
    batches = []

    def fake_embedding(**kwargs):
        batches.append(list(kwargs["input"]))
        return SimpleNamespace(data=[{"embedding": [float(t)]} for t in kwargs["input"]])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    texts = [str(i) for i in range(250)]
    vectors = LiteLLMEmbedder(model="e", batch_size=100).embed(texts)

    assert [len(b) for b in batches] == [100, 100, 50]
    assert vectors == [[float(i)] for i in range(250)]


def test_embedder_with_no_texts_makes_no_call(monkeypatch):
    monkeypatch.setattr(litellm, "embedding", lambda **kw: pytest.fail("called"))
    assert LiteLLMEmbedder(model="e").embed([]) == []


def test_embedder_wraps_errors_and_reads_env(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("bad key")

    monkeypatch.setattr(litellm, "embedding", boom)
    with pytest.raises(LLMError, match="bad key"):
        LiteLLMEmbedder(model="e").embed(["x"])

    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_DIMENSIONS", raising=False)
    embedder = LiteLLMEmbedder.from_env()
    assert embedder.model == "gemini/gemini-embedding-001"
    assert embedder.dimensions == 768


def test_embedder_passes_dimensions_to_provider(monkeypatch):
    seen = {}

    def fake_embedding(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.0] * 768}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    LiteLLMEmbedder(model="e", dimensions=768).embed(["x"])
    assert seen["dimensions"] == 768


def test_embedder_omits_dimensions_when_not_set(monkeypatch):
    seen = {}

    def fake_embedding(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.0]}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    LiteLLMEmbedder(model="e").embed(["x"])
    assert "dimensions" not in seen


def test_embedder_dimensions_come_from_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")
    assert LiteLLMEmbedder.from_env().dimensions == 1536


def test_embedder_rejects_vectors_of_the_wrong_size(monkeypatch):
    monkeypatch.setattr(
        litellm, "embedding", lambda **kw: SimpleNamespace(data=[{"embedding": [0.0] * 3}])
    )
    with pytest.raises(LLMError, match="dimension"):
        LiteLLMEmbedder(model="e", dimensions=768).embed(["x"])


def _tool_response(content, calls):
    message = SimpleNamespace(content=content, tool_calls=[
        SimpleNamespace(id=i, function=SimpleNamespace(name=n, arguments=a)) for i, n, a in calls
    ])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_complete_with_tools_offers_tools_and_parses_calls(monkeypatch):
    seen = {}

    def fake_completion(**kwargs):
        seen.update(kwargs)
        return _tool_response(None, [("c1", "lookup_player", '{"name": "Jokic"}'), ("c2", "get_standings", "not json")])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    tools = [{"type": "function", "function": {"name": "lookup_player"}}]
    reply = LiteLLMClient(model="m").complete_with_tools([{"role": "user", "content": "x"}], tools)

    assert seen["tools"] == tools
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("c1", "lookup_player", {"name": "Jokic"}), ("c2", "get_standings", {}),
    ]


def test_complete_with_tools_returns_a_plain_answer(monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **kw: _tool_response("done", []))
    reply = LiteLLMClient(model="m").complete_with_tools([], [{"type": "function"}])
    assert reply.content == "done" and reply.tool_calls == ()


def test_complete_with_tools_rejects_an_empty_turn(monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **kw: _tool_response(None, []))
    with pytest.raises(LLMError):
        LiteLLMClient(model="m", max_retries=0).complete_with_tools([], [{"type": "function"}])
