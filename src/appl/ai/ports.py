from dataclasses import dataclass
from typing import Optional, Protocol

from .chunker import Chunk


@dataclass(frozen=True)
class VectorRecord:
    chunk: Chunk
    vector: list[float]


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float
    collection_id: str


class LLMClient(Protocol):
    def complete(self, messages: list[dict]) -> str: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def replace_collection(
        self, collection_id: str, records: list[VectorRecord]
    ) -> None: ...

    def search(
        self, collection_ids: list[str], query_vector: list[float], k: int
    ) -> list[SearchResult]: ...

    def last_synced(self, collection_id: str) -> Optional[str]: ...
