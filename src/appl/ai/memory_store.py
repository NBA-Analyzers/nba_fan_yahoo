import math
from datetime import datetime, timezone
from typing import Optional

from .ports import SearchResult, VectorRecord


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryVectorStore:
    def __init__(self):
        self._records: dict[str, list[VectorRecord]] = {}
        self._synced: dict[str, str] = {}

    def replace_collection(self, collection_id: str, records: list[VectorRecord]) -> None:
        self._records[collection_id] = list(records)
        self._synced[collection_id] = datetime.now(timezone.utc).isoformat()

    def search(
        self, collection_ids: list[str], query_vector: list[float], k: int
    ) -> list[SearchResult]:
        results = [
            SearchResult(r.chunk, _cosine(query_vector, r.vector), cid)
            for cid in collection_ids
            for r in self._records.get(cid, [])
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def last_synced(self, collection_id: str) -> Optional[str]:
        return self._synced.get(collection_id)
