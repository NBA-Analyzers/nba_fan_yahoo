import logging
import os
import time
from typing import Callable, Optional

import litellm

from .redact import scrub_secrets

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "gemini/gemini-3.8-flash"
DEFAULT_EMBEDDING_MODEL = "gemini/gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 768  # Firestore vector indexes allow at most 2048
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0

_TRANSIENT = (
    litellm.ServiceUnavailableError,
    litellm.Timeout,
    litellm.RateLimitError,
    litellm.InternalServerError,
    litellm.APIConnectionError,
)


class LLMError(Exception):
    pass


def _call_with_retries(call: Callable[[], object], max_retries: int, delay: float, sleep):
    """Run `call`, retrying transient provider errors with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return call()
        except _TRANSIENT:
            if attempt == max_retries:
                raise
            sleep(delay * (2**attempt))


class LiteLLMClient:
    def __init__(
        self,
        model: str,
        fallback_model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._sleep = sleep

    @classmethod
    def from_env(cls) -> "LiteLLMClient":
        return cls(
            os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL),
            fallback_model=os.environ.get("LLM_FALLBACK_MODEL") or None,
            timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        )

    def complete(self, messages: list[dict]) -> str:
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_error: Optional[Exception] = None
        for model in models:
            try:
                return self._complete_with(model, messages)
            except Exception as e:
                last_error = e
                logger.warning("LLM call to %s failed: %s", model, scrub_secrets(str(e)))
        # `from None`: the original exception text can contain the request URL (with the key)
        raise LLMError(f"LLM call failed: {scrub_secrets(str(last_error))}") from None

    def _complete_with(self, model: str, messages: list[dict]) -> str:
        response = _call_with_retries(
            lambda: litellm.completion(
                model=model,
                messages=messages,
                timeout=self.timeout,
                num_retries=0,
            ),
            self.max_retries,
            self.retry_delay,
            self._sleep,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty answer")
        return content


class LiteLLMEmbedder:
    def __init__(
        self,
        model: str,
        batch_size: int = 100,
        dimensions: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.batch_size = batch_size
        self.dimensions = dimensions
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._sleep = sleep

    @classmethod
    def from_env(cls) -> "LiteLLMEmbedder":
        return cls(
            os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            dimensions=int(
                os.environ.get("EMBEDDING_DIMENSIONS", DEFAULT_EMBEDDING_DIMENSIONS)
            ),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        extra = {"dimensions": self.dimensions} if self.dimensions else {}
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                response = _call_with_retries(
                    lambda: litellm.embedding(
                        model=self.model,
                        input=batch,
                        timeout=self.timeout,
                        num_retries=0,
                        **extra,
                    ),
                    self.max_retries,
                    self.retry_delay,
                    self._sleep,
                )
                vectors.extend(item["embedding"] for item in response.data)
            except Exception as e:
                raise LLMError(f"Embedding call failed: {scrub_secrets(str(e))}") from None
        if self.dimensions and any(len(v) != self.dimensions for v in vectors):
            raise LLMError(
                f"Embedding dimension mismatch: expected {self.dimensions}, "
                f"got {len(vectors[0])}"
            )
        return vectors
