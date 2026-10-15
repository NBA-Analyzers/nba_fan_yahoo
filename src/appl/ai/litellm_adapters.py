import json
import logging
import os
import time
from typing import Callable, Iterator, Optional

import litellm

from ..ingest.http import with_retry
from .ports import LLMReply, ToolCall
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


def _optional(value: Optional[str], cast):
    return cast(value) if value not in (None, "") else None


def _call_with_retries(call: Callable[[], object], max_retries: int, delay: float, sleep):
    """Run `call`, retrying transient provider errors with exponential backoff."""
    return with_retry(call, attempts=max_retries + 1, delay=delay, retry_on=_TRANSIENT,
                      sleep=sleep, label="LLM")


class LiteLLMClient:
    def __init__(
        self,
        model: str,
        fallback_model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """`temperature` and `max_tokens` are left to the provider unless set (reasoning
        models spend part of max_tokens on thinking, so a low cap can empty the answer)."""
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.max_tokens = max_tokens
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
            temperature=_optional(os.environ.get("LLM_TEMPERATURE"), float),
            max_tokens=_optional(os.environ.get("LLM_MAX_TOKENS"), int),
        )

    def complete(self, messages: list[dict]) -> str:
        return self._first_working(lambda model: self._complete_with(model, messages))

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        """One model turn with `tools` on offer: a final answer or tool calls to run."""
        return self._first_working(lambda model: self._turn_with(model, messages, tools))

    def _first_working(self, call: Callable[[str], object]):
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_error: Optional[Exception] = None
        for model in models:
            try:
                return call(model)
            except Exception as e:
                last_error = e
                logger.warning("LLM call to %s failed: %s", model, scrub_secrets(str(e)))
        # `from None`: the original exception text can contain the request URL (with the key)
        raise LLMError(f"LLM call failed: {scrub_secrets(str(last_error))}") from None

    def _options(self, tools: Optional[list[dict]] = None) -> dict:
        options = {}
        if tools:
            options["tools"] = tools
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.max_tokens is not None:
            options["max_tokens"] = self.max_tokens
        return options

    def _message(self, model: str, messages: list[dict], tools: Optional[list[dict]] = None):
        options = self._options(tools)
        response = _call_with_retries(
            lambda: litellm.completion(
                model=model,
                messages=messages,
                timeout=self.timeout,
                num_retries=0,
                **options,
            ),
            self.max_retries,
            self.retry_delay,
            self._sleep,
        )
        return response.choices[0].message

    def _complete_with(self, model: str, messages: list[dict]) -> str:
        content = self._message(model, messages).content
        if not content:
            raise ValueError("LLM returned an empty answer")
        return content

    @staticmethod
    def _reply_from(message) -> LLMReply:
        calls = []
        for call in getattr(message, "tool_calls", None) or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except ValueError:
                arguments = {}
            calls.append(ToolCall(call.id, call.function.name,
                                  arguments if isinstance(arguments, dict) else {}))
        if not calls and not message.content:
            raise ValueError("LLM returned an empty answer")
        return LLMReply(content=message.content or "", tool_calls=tuple(calls))

    def _turn_with(self, model: str, messages: list[dict], tools: list[dict]) -> LLMReply:
        return self._reply_from(self._message(model, messages, tools))

    # --- streaming ----------------------------------------------------------

    def stream_turn(self, messages: list[dict], tools: Optional[list[dict]] = None) -> Iterator:
        """One model turn as it is produced: yields text pieces (str) as they arrive and
        finally the whole turn as an LLMReply (its tool calls included). The fallback model
        is tried only if the first one fails before any text went out."""
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_error: Optional[Exception] = None
        for model in models:
            sent_text = False
            try:
                for item in self._stream_with(model, messages, tools):
                    sent_text = sent_text or isinstance(item, str)
                    yield item
                return
            except Exception as e:
                last_error = e
                logger.warning("LLM stream from %s failed: %s", model, scrub_secrets(str(e)))
                if sent_text:
                    break
        raise LLMError(f"LLM call failed: {scrub_secrets(str(last_error))}") from None

    def _stream_with(self, model: str, messages: list[dict], tools: Optional[list[dict]]) -> Iterator:
        options = self._options(tools)
        stream = _call_with_retries(
            lambda: litellm.completion(
                model=model,
                messages=messages,
                timeout=self.timeout,
                num_retries=0,
                stream=True,
                **options,
            ),
            self.max_retries,
            self.retry_delay,
            self._sleep,
        )
        chunks = []
        for chunk in stream:
            chunks.append(chunk)
            choices = getattr(chunk, "choices", None) or []
            text = getattr(choices[0].delta, "content", None) if choices else None
            if text:
                yield text
        built = litellm.stream_chunk_builder(chunks, messages=messages)
        yield self._reply_from(built.choices[0].message)


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
