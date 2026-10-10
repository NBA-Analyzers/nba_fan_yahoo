import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from .chunker import Chunk
from .ports import SearchResult, VectorRecord

CHUNKS = "chunks"
GENERATIONS = "generations"
DISTANCE_FIELD = "_distance"


class FirestoreVectorStore:
    """Layout:
      <root>/<collection_id>  {active_generation, last_synced, chunk_count, content_hash}
        generations/<gen>  {created_at}
          chunks/<auto-id>  {text, source, index, embedding}

    A replace writes a whole new generation, then flips `active_generation` on the parent
    (a single-document write), then deletes the older generations. A failure part-way
    leaves the previous generation serving searches.

    Collections written before generations existed keep their chunks directly under
    <root>/<collection_id>/chunks; they are searched there until the next replace.

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

    def _meta(self, collection_id: str) -> dict:
        snap = self._doc(collection_id).get()
        return snap.to_dict() if snap.exists else {}

    def _chunks(self, collection_id: str, meta: dict):
        doc = self._doc(collection_id)
        gen = meta.get("active_generation")
        if gen:
            return doc.collection(GENERATIONS).document(gen).collection(CHUNKS)
        return doc.collection(CHUNKS)  # legacy layout

    def replace_collection(self, collection_id: str, records: list[VectorRecord],
                           content_hash: Optional[str] = None) -> None:
        doc = self._doc(collection_id)
        now = datetime.now(timezone.utc).isoformat()
        gen = f"{now[:19].replace(':', '')}-{uuid.uuid4().hex[:8]}"
        gen_ref = doc.collection(GENERATIONS).document(gen)
        gen_ref.set({"created_at": now})
        chunks = gen_ref.collection(CHUNKS)
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
        # The swap: from here on searches read the new generation
        doc.set(
            {
                "active_generation": gen,
                "last_synced": now,
                "chunk_count": len(records),
                "content_hash": content_hash,
            }
        )
        self._delete_generations(collection_id, keep=gen)

    def delete_collection(self, collection_id: str) -> None:
        self._delete_generations(collection_id, keep=None)
        self._commit_in_batches([("delete", self._doc(collection_id), None)])

    def _delete_generations(self, collection_id: str, keep: Optional[str]) -> None:
        """Remove every generation except `keep` (including ones a failed replace left
        behind) and any legacy chunks."""
        doc = self._doc(collection_id)
        ops = [("delete", s.reference, None) for s in doc.collection(CHUNKS).stream()]
        for gen_snap in doc.collection(GENERATIONS).stream():
            if gen_snap.reference.path.rsplit("/", 1)[-1] == keep:
                continue
            ops += [("delete", s.reference, None)
                    for s in gen_snap.reference.collection(CHUNKS).stream()]
            ops.append(("delete", gen_snap.reference, None))
        self._commit_in_batches(ops)

    def search(
        self, collection_ids: list[str], query_vector: list[float], k: int
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for collection_id in collection_ids:
            query = self._chunks(collection_id, self._meta(collection_id)).find_nearest(
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
        return self._meta(collection_id).get("last_synced")

    def content_hash(self, collection_id: str) -> Optional[str]:
        return self._meta(collection_id).get("content_hash")

    def _commit_in_batches(self, ops: list[tuple]) -> None:
        for start in range(0, len(ops), self.batch_size):
            batch = self.client.batch()
            for op, ref, data in ops[start : start + self.batch_size]:
                if op == "set":
                    batch.set(ref, data)
                else:
                    batch.delete(ref)
            batch.commit()
