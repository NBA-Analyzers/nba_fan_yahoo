from datetime import datetime, timezone
from typing import Optional

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from .chunker import Chunk
from .ports import SearchResult, VectorRecord

CHUNKS = "chunks"
DISTANCE_FIELD = "_distance"


class FirestoreVectorStore:
    """Layout: <root>/<collection_id> {last_synced}  ->  chunks/<auto-id> {text, source, index, embedding}

    Needs a vector index on `chunks.embedding` (collection group, dimension = embedding size):
      gcloud firestore indexes composite create --collection-group=chunks \
        --query-scope=COLLECTION --field-config=field-path=embedding,vector-config='{"dimension":"768","flat":"{}"}'
    """

    def __init__(self, client, root: str = "rag_collections", batch_size: int = 400):
        self.client = client
        self.root = root
        self.batch_size = batch_size

    def _doc(self, collection_id: str):
        return self.client.collection(self.root).document(collection_id)

    def replace_collection(self, collection_id: str, records: list[VectorRecord]) -> None:
        doc = self._doc(collection_id)
        chunks = doc.collection(CHUNKS)

        self._commit_in_batches(
            [("delete", snap.reference, None) for snap in chunks.stream()]
        )
        self._commit_in_batches(
            [
                (
                    "set",
                    chunks.document(),
                    {
                        "text": r.chunk.text,
                        "source": r.chunk.source,
                        "index": r.chunk.index,
                        "embedding": Vector(r.vector),
                    },
                )
                for r in records
            ]
        )
        doc.set(
            {
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "chunk_count": len(records),
            }
        )

    def search(
        self, collection_ids: list[str], query_vector: list[float], k: int
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for collection_id in collection_ids:
            query = self._doc(collection_id).collection(CHUNKS).find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_vector),
                limit=k,
                distance_measure=DistanceMeasure.COSINE,
                distance_result_field=DISTANCE_FIELD,
            )
            for snap in query.stream():
                data = snap.to_dict()
                results.append(
                    SearchResult(
                        chunk=Chunk(
                            text=data["text"], source=data["source"], index=data["index"]
                        ),
                        score=1.0 - data[DISTANCE_FIELD],
                        collection_id=collection_id,
                    )
                )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def last_synced(self, collection_id: str) -> Optional[str]:
        snap = self._doc(collection_id).get()
        return snap.to_dict().get("last_synced") if snap.exists else None

    def _commit_in_batches(self, ops: list[tuple]) -> None:
        for start in range(0, len(ops), self.batch_size):
            batch = self.client.batch()
            for op, ref, data in ops[start : start + self.batch_size]:
                if op == "set":
                    batch.set(ref, data)
                else:
                    batch.delete(ref)
            batch.commit()
