import os

import litellm

DEFAULT_LLM_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "gemini/text-embedding-004"


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
    def __init__(self, model: str, batch_size: int = 100):
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_env(cls) -> "LiteLLMEmbedder":
        return cls(os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL))

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                response = litellm.embedding(model=self.model, input=batch)
                vectors.extend(item["embedding"] for item in response.data)
            except Exception as e:
                raise LLMError(f"Embedding call failed: {e}") from e
        return vectors
