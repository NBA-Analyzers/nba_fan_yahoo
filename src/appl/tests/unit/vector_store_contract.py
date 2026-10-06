"""Behavior every VectorStore implementation must satisfy.
Import `VectorStoreContract` into a test module and provide a `store` fixture."""
from appl.ai.chunker import Chunk
from appl.ai.ports import VectorRecord


def rec(text, vector, source="s", index=0):
    return VectorRecord(chunk=Chunk(text=text, source=source, index=index), vector=vector)


class VectorStoreContract:
    def test_search_on_empty_store_returns_nothing(self, store):
        assert store.search(["a"], [1.0, 0.0], k=3) == []

    def test_search_ranks_by_similarity(self, store):
        store.replace_collection(
            "a",
            [rec("far", [0.0, 1.0], index=0), rec("near", [1.0, 0.1], index=1)],
        )
        results = store.search(["a"], [1.0, 0.0], k=2)
        assert [r.chunk.text for r in results] == ["near", "far"]
        assert results[0].score >= results[1].score
        assert results[0].collection_id == "a"

    def test_k_limits_results(self, store):
        store.replace_collection(
            "a", [rec(f"t{i}", [1.0, i * 0.1], index=i) for i in range(5)]
        )
        assert len(store.search(["a"], [1.0, 0.0], k=2)) == 2

    def test_replace_collection_drops_old_records(self, store):
        store.replace_collection("a", [rec("old", [1.0, 0.0])])
        store.replace_collection("a", [rec("new", [1.0, 0.0])])
        texts = [r.chunk.text for r in store.search(["a"], [1.0, 0.0], k=10)]
        assert texts == ["new"]

    def test_collections_are_isolated(self, store):
        store.replace_collection("a", [rec("in-a", [1.0, 0.0])])
        store.replace_collection("b", [rec("in-b", [1.0, 0.0])])
        assert [r.chunk.text for r in store.search(["a"], [1.0, 0.0], k=5)] == ["in-a"]

    def test_search_across_multiple_collections(self, store):
        store.replace_collection("a", [rec("in-a", [1.0, 0.0])])
        store.replace_collection("b", [rec("in-b", [0.9, 0.1])])
        results = store.search(["a", "b"], [1.0, 0.0], k=5)
        assert {r.chunk.text for r in results} == {"in-a", "in-b"}
        assert {r.collection_id for r in results} == {"a", "b"}

    def test_unknown_collection_is_ignored(self, store):
        store.replace_collection("a", [rec("in-a", [1.0, 0.0])])
        assert len(store.search(["a", "missing"], [1.0, 0.0], k=5)) == 1

    def test_last_synced_is_none_until_written(self, store):
        assert store.last_synced("a") is None
        store.replace_collection("a", [rec("x", [1.0, 0.0])])
        assert store.last_synced("a") is not None

    def test_chunk_metadata_round_trips(self, store):
        store.replace_collection("a", [rec("x", [1.0, 0.0], source="rules.pdf", index=7)])
        chunk = store.search(["a"], [1.0, 0.0], k=1)[0].chunk
        assert (chunk.text, chunk.source, chunk.index) == ("x", "rules.pdf", 7)
