from types import SimpleNamespace

import litellm
import pytest

from appl.ai.litellm_adapters import LiteLLMClient, LiteLLMEmbedder, LLMError
from appl.ai.redact import scrub_secrets


def _ok(text="fine"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _unavailable(model="m"):
    return litellm.ServiceUnavailableError("high demand", llm_provider="gemini", model=model)


def _timeout(model="m"):
    return litellm.Timeout("slow", model=model, llm_provider="gemini")


def _auth(model="m"):
    return litellm.AuthenticationError("bad key", llm_provider="gemini", model=model)


class Script:
    """Replaces litellm.completion: pops the next outcome (exception or response) per call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(**kw):
    sleeps = []
    c = LiteLLMClient(model="main", sleep=sleeps.append, **kw)
    c.sleeps = sleeps
    return c


MSG = [{"role": "user", "content": "x"}]


# ---------- retries ----------
def test_transient_error_is_retried_then_succeeds(monkeypatch):
    script = Script(_unavailable(), _timeout(), _ok("third time"))
    monkeypatch.setattr(litellm, "completion", script)
    c = client(max_retries=2)
    assert c.complete(MSG) == "third time"
    assert len(script.calls) == 3


def test_backoff_grows_between_retries(monkeypatch):
    monkeypatch.setattr(litellm, "completion", Script(_unavailable(), _unavailable(), _ok()))
    c = client(max_retries=2, retry_delay=1.0)
    c.complete(MSG)
    assert c.sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries(monkeypatch):
    script = Script(_unavailable(), _unavailable(), _unavailable())
    monkeypatch.setattr(litellm, "completion", script)
    with pytest.raises(LLMError):
        client(max_retries=2).complete(MSG)
    assert len(script.calls) == 3


def test_permanent_errors_are_not_retried(monkeypatch):
    script = Script(_auth())
    monkeypatch.setattr(litellm, "completion", script)
    with pytest.raises(LLMError):
        client(max_retries=3).complete(MSG)
    assert len(script.calls) == 1


def test_litellm_internal_retries_are_disabled_and_timeout_is_passed(monkeypatch):
    script = Script(_ok())
    monkeypatch.setattr(litellm, "completion", script)
    client(timeout=12).complete(MSG)
    assert script.calls[0]["timeout"] == 12
    assert script.calls[0]["num_retries"] == 0


# ---------- fallback ----------
def test_fallback_model_is_used_when_primary_keeps_failing(monkeypatch):
    script = Script(_unavailable(), _unavailable(), _ok("from fallback"))
    monkeypatch.setattr(litellm, "completion", script)
    c = client(max_retries=1, fallback_model="backup")
    assert c.complete(MSG) == "from fallback"
    assert [call["model"] for call in script.calls] == ["main", "main", "backup"]


def test_fallback_is_used_even_for_permanent_primary_errors(monkeypatch):
    script = Script(_auth(), _ok("from fallback"))
    monkeypatch.setattr(litellm, "completion", script)
    assert client(fallback_model="backup").complete(MSG) == "from fallback"


def test_error_when_primary_and_fallback_both_fail(monkeypatch):
    monkeypatch.setattr(
        litellm, "completion", Script(_unavailable(), _unavailable("backup"))
    )
    with pytest.raises(LLMError):
        client(max_retries=0, fallback_model="backup").complete(MSG)


def test_fallback_read_from_env(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gemini/other")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    c = LiteLLMClient.from_env()
    assert (c.fallback_model, c.timeout) == ("gemini/other", 45)
    monkeypatch.delenv("LLM_FALLBACK_MODEL")
    assert LiteLLMClient.from_env().fallback_model is None


# ---------- embedder resilience ----------
def test_embedder_retries_transient_errors(monkeypatch):
    calls = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _unavailable()
        return SimpleNamespace(data=[{"embedding": [1.0]}])

    monkeypatch.setattr(litellm, "embedding", flaky)
    sleeps = []
    e = LiteLLMEmbedder(model="e", sleep=sleeps.append)
    assert e.embed(["x"]) == [[1.0]]
    assert len(calls) == 2 and calls[0]["num_retries"] == 0 and "timeout" in calls[0]


# ---------- secrets never leak ----------
def test_scrub_removes_key_in_urls_and_known_formats():
    text = "503 for url 'https://x/v1beta/models/m:generateContent?key=AQ.Ab8RN6secretvalue123' bearer"
    assert "secretvalue" not in scrub_secrets(text)
    assert "key=***" in scrub_secrets(text)
    assert "sk-abcdefghijklmnop1234" not in scrub_secrets("token sk-abcdefghijklmnop1234 ok")
    assert "AIzaSyA1234567890abcdefghij" not in scrub_secrets("k AIzaSyA1234567890abcdefghij")
    assert "Bearer abc.def" not in scrub_secrets("Authorization: Bearer abc.def")


def test_scrub_removes_values_of_secret_env_vars(monkeypatch):
    monkeypatch.setenv("MY_SERVICE_API_KEY", "super-secret-value-9999")
    assert "super-secret-value-9999" not in scrub_secrets("oops super-secret-value-9999 here")


def test_scrub_leaves_normal_text_alone():
    assert scrub_secrets("model gemini-3.8-flash is overloaded") == "model gemini-3.8-flash is overloaded"


def test_llm_error_message_never_contains_the_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.Ab8RN6verysecretkeyvalue")
    err = litellm.ServiceUnavailableError(
        "Server error for url https://g/x?key=AQ.Ab8RN6verysecretkeyvalue",
        llm_provider="gemini",
        model="m",
    )
    monkeypatch.setattr(litellm, "completion", Script(err))
    with pytest.raises(LLMError) as exc:
        client(max_retries=0).complete(MSG)
    assert "verysecretkeyvalue" not in str(exc.value)
