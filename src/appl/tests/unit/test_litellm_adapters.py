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
    assert LiteLLMClient.from_env().model == "gemini/gemini-2.5-flash"
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
    assert LiteLLMEmbedder.from_env().model == "gemini/text-embedding-004"
