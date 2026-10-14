import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from .chunker import Chunk, chunk_json, chunk_text
from .ports import Embedder, SearchResult, VectorRecord, VectorStore

logger = logging.getLogger(__name__)


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


def content_hash(documents: list[Document]) -> str:
    payload = json.dumps(
        [[d.source, d.text, d.data] for d in documents], sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RetrievalService:
    def __init__(self, embedder: Embedder, store: VectorStore, top_k: int = 5):
        self.embedder = embedder
        self.store = store
        self.top_k = top_k

    def index(self, collection_id: str, documents: list[Document], force: bool = False) -> bool:
        """Embed and store `documents` as the collection's whole content. Returns False
        (and embeds nothing) when the content is identical to what is already stored."""
        digest = content_hash(documents)
        if not force and self.store.content_hash(collection_id) == digest:
            logger.info("%s unchanged, skipped", collection_id)
            return False
        chunks = [c for doc in documents for c in doc.to_chunks()]
        vectors = self.embedder.embed([c.text for c in chunks]) if chunks else []
        records = [VectorRecord(chunk=c, vector=v) for c, v in zip(chunks, vectors)]
        self.store.replace_collection(collection_id, records, content_hash=digest)
        logger.info("%s indexed: %d chunks", collection_id, len(records))
        return True

    def retrieve(
        self, query: str, collection_ids: list[str], k: Optional[int] = None
    ) -> list[SearchResult]:
        if not collection_ids:
            return []
        query_vector = self.embedder.embed([query])[0]
        return self.store.search(collection_ids, query_vector, k or self.top_k)
