import pytest

from appl.ai.retrieval import Document, RetrievalService


@pytest.fixture
def service(embedder, memory_store):
    return RetrievalService(embedder, memory_store, top_k=2)


def test_index_text_document_then_retrieve_it(service):
    service.index("general", [Document(source="rules.pdf", text="points count one each")])
    results = service.retrieve("how many points", ["general"])
    assert results[0].chunk.source == "rules.pdf"
    assert "points" in results[0].chunk.text


def test_index_json_document_creates_chunk_per_record(service, memory_store):
    docs = [Document(source="stats.json", data=[{"name": "Curry"}, {"name": "James"}])]
    service.index("general", docs)
    texts = [r.chunk.text for r in memory_store.search(["general"], [1.0] + [0.0] * 31, k=10)]
    assert len(texts) == 2


def test_all_chunks_are_embedded_in_one_call(service, embedder):
    docs = [Document(source="a", text="one"), Document(source="b", text="two")]
    service.index("c", docs)
    assert len(embedder.calls) == 1 and len(embedder.calls[0]) == 2


def test_reindex_replaces_previous_content(service):
    service.index("c", [Document(source="a", text="alpha")])
    service.index("c", [Document(source="a", text="beta")])
    texts = [r.chunk.text for r in service.retrieve("alpha beta", ["c"])]
    assert texts == ["beta"]


def test_indexing_nothing_clears_the_collection(service):
    service.index("c", [Document(source="a", text="alpha")])
    service.index("c", [])
    assert service.retrieve("alpha", ["c"]) == []


def test_retrieve_returns_most_relevant_first_and_respects_top_k(service):
    service.index(
        "c",
        [
            Document(source="1", text="basketball rebounds and blocks"),
            Document(source="2", text="cooking pasta recipe"),
            Document(source="3", text="basketball assists and steals"),
        ],
    )
    results = service.retrieve("basketball rebounds", ["c"])
    assert len(results) == 2
    assert results[0].chunk.source == "1"


def test_retrieve_across_collections(service):
    service.index("league_1", [Document(source="l", text="my team roster")])
    service.index("general", [Document(source="g", text="roster rules")])
    sources = {r.chunk.source for r in service.retrieve("roster", ["league_1", "general"])}
    assert sources == {"l", "g"}


def test_retrieve_without_collections_skips_embedding(service, embedder):
    assert service.retrieve("anything", []) == []
    assert embedder.calls == []


def test_document_needs_text_or_data():
    with pytest.raises(ValueError):
        Document(source="x")
