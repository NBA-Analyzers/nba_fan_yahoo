import hashlib
import math

import pytest

from appl.ai.memory_store import InMemoryVectorStore
from appl.ai.ports import LLMReply


class FakeEmbedder:
    """Deterministic bag-of-words embedder: texts sharing words are close."""

    DIM = 32

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.DIM
        for word in text.lower().split():
            h = int(hashlib.md5(word.strip(".,:").encode()).hexdigest(), 16)
            v[h % self.DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


class FakeLLMClient:
    def __init__(self, reply: str = "ok"):
        self.reply = reply
        self.calls: list[list[dict]] = []
        self.turns: list[LLMReply] = []
        self.tools_offered: list[dict] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append([dict(m) for m in messages])
        return self.reply

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        """Plays the scripted `turns` in order, then answers with `reply`."""
        self.calls.append([dict(m) for m in messages])
        self.tools_offered = tools
        return self.turns.pop(0) if self.turns else LLMReply(content=self.reply)


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def llm():
    return FakeLLMClient()


@pytest.fixture
def memory_store():
    return InMemoryVectorStore()
