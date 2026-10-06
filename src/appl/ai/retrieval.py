from dataclasses import dataclass
from typing import Any, Optional

from .chunker import Chunk, chunk_json, chunk_text
from .ports import Embedder, SearchResult, VectorRecord, VectorStore


@dataclass(frozen=True)
class Document:
    source: str
    text: Optional[str] = None
    data: Any = None

    def __post_init__(self):
        if self.text is None and self.data is None:
            raise ValueError("Document needs text or data")

    def to_chunks(self) -> list[Chunk]:
        if self.text is not None:
            return chunk_text(self.text, self.source)
        return chunk_json(self.data, self.source)


class RetrievalService:
    def __init__(self, embedder: Embedder, store: VectorStore, top_k: int = 5):
        self.embedder = embedder
        self.store = store
        self.top_k = top_k

    def index(self, collection_id: str, documents: list[Document]) -> None:
        chunks = [c for doc in documents for c in doc.to_chunks()]
        vectors = self.embedder.embed([c.text for c in chunks]) if chunks else []
        records = [VectorRecord(chunk=c, vector=v) for c, v in zip(chunks, vectors)]
        self.store.replace_collection(collection_id, records)

    def retrieve(
        self, query: str, collection_ids: list[str], k: Optional[int] = None
    ) -> list[SearchResult]:
        if not collection_ids:
            return []
        query_vector = self.embedder.embed([query])[0]
        return self.store.search(collection_ids, query_vector, k or self.top_k)
