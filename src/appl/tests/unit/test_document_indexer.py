import json

import pytest

from appl.ai.document_indexer import DocumentIndexer
from appl.ai.retrieval import RetrievalService


@pytest.fixture
def indexer(embedder, memory_store):
    retrieval = RetrievalService(embedder, memory_store, top_k=10)
    return DocumentIndexer(retrieval, pdf_extractor=lambda path: f"PDF TEXT from {path}")


def _all(store, collection):
    return store.search([collection], [1.0] + [0.0] * 31, k=100)


def test_update_league_files_indexes_each_file_into_league_collection(indexer, memory_store):
    indexer.update_league_files(
        "42", {"roster": {"players": ["Curry"]}, "standings": [{"team": "A"}]}
    )
    results = _all(memory_store, "league_42")
    assert {r.chunk.source for r in results} == {"roster.json", "standings.json"}
    assert _all(memory_store, "general") == []


def test_update_league_files_replaces_previous_sync(indexer, memory_store):
    indexer.update_league_files("42", {"roster": {"p": "old"}})
    indexer.update_league_files("42", {"roster": {"p": "new"}})
    texts = [r.chunk.text for r in _all(memory_store, "league_42")]
    assert len(texts) == 1 and "new" in texts[0]


def test_update_rules_indexes_pdf_text_into_general(indexer, memory_store):
    indexer.update_rules("/x/rules.pdf")
    results = _all(memory_store, "general")
    assert results and results[0].chunk.source == "rules.pdf"
    assert "PDF TEXT from /x/rules.pdf" in results[0].chunk.text


def test_update_player_stats_indexes_json_pdf_and_schedule(indexer, memory_store, tmp_path):
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps([{"name": "Curry"}]), encoding="utf-8")
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps({"week1": ["GSW vs LAL"]}), encoding="utf-8")

    indexer.update_player_stats(str(stats), pdf_path="/x/rules.pdf", schedule_path=str(schedule))

    sources = {r.chunk.source for r in _all(memory_store, "general")}
    assert sources == {"stats.json", "rules.pdf", "schedule.json"}


def test_update_player_stats_pdf_and_schedule_are_optional(indexer, memory_store, tmp_path):
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps([{"name": "Curry"}]), encoding="utf-8")
    indexer.update_player_stats(str(stats))
    assert {r.chunk.source for r in _all(memory_store, "general")} == {"stats.json"}


def test_missing_stats_file_raises(indexer, tmp_path):
    with pytest.raises(FileNotFoundError):
        indexer.update_player_stats(str(tmp_path / "nope.json"))
