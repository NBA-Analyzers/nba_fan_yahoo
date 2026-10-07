import os
from typing import Optional

import litellm

DEFAULT_LLM_MODEL = "gemini/gemini-3.8-flash"
DEFAULT_EMBEDDING_MODEL = "gemini/gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 768  # Firestore vector indexes allow at most 2048


class LLMError(Exception):
    pass


class LiteLLMClient:
    def __init__(self, model: str):
        self.model = model

    @classmethod
    def from_env(cls) -> "LiteLLMClient":
        return cls(os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL))

    def complete(self, messages: list[dict]) -> str:
        try:
            response = litellm.completion(model=self.model, messages=messages)
            content = response.choices[0].message.content
        except Exception as e:
            raise LLMError(f"LLM call failed: {e}") from e
        if not content:
            raise LLMError("LLM returned an empty answer")
        return content


class LiteLLMEmbedder:
    def __init__(
        self, model: str, batch_size: int = 100, dimensions: Optional[int] = None
    ):
        self.model = model
        self.batch_size = batch_size
        self.dimensions = dimensions

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
                response = litellm.embedding(model=self.model, input=batch, **extra)
                vectors.extend(item["embedding"] for item in response.data)
            except Exception as e:
                raise LLMError(f"Embedding call failed: {e}") from e
        if self.dimensions and any(len(v) != self.dimensions for v in vectors):
            raise LLMError(
                f"Embedding dimension mismatch: expected {self.dimensions}, "
                f"got {len(vectors[0])}"
            )
        return vectors
