import pytest

from appl.ai.document_indexer import DocumentIndexer
from appl.ai.retrieval import RetrievalService


class CountingEmbedder:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def embed(self, texts):
        self.calls += 1
        return self.inner.embed(texts)


@pytest.fixture
def counting(embedder):
    return CountingEmbedder(embedder)


@pytest.fixture
def indexer(counting, memory_store):
    retrieval = RetrievalService(counting, memory_store, top_k=10)
    return DocumentIndexer(retrieval, pdf_extractor=lambda path: f"PDF TEXT from {path}")


def _all(store, collection):
    return store.search([collection], [1.0] + [0.0] * 31, k=100)


GAMES = [
    {"date": "2026-10-21", "home_team": "Lakers", "away_team": "Warriors", "game_id": "1"},
    {"date": "2026-10-21", "home_team": "Celtics", "away_team": "Knicks", "game_id": "2"},
]


def test_update_league_files_indexes_each_file_into_league_collection(indexer, memory_store):
    indexer.update_league_files(
        "42", {"roster": {"players": ["Curry"]}, "standings": [{"team": "A"}]}
    )
    results = _all(memory_store, "league_42")
    assert {r.chunk.source for r in results} == {"roster.json", "standings.json"}
    assert _all(memory_store, "general_stats") == []


def test_update_league_files_replaces_previous_sync(indexer, memory_store):
    indexer.update_league_files("42", {"roster": {"p": "old"}})
    indexer.update_league_files("42", {"roster": {"p": "new"}})
    texts = [r.chunk.text for r in _all(memory_store, "league_42")]
    assert len(texts) == 1 and "new" in texts[0]


def test_rules_go_to_their_own_collection(indexer, memory_store):
    assert indexer.update_rules("/x/rules.pdf") is True
    results = _all(memory_store, "general_rules")
    assert results and results[0].chunk.source == "rules.pdf"
    assert "PDF TEXT from /x/rules.pdf" in results[0].chunk.text


def test_refreshing_one_shared_source_keeps_the_others(indexer, memory_store):
    indexer.update_rules("/x/rules.pdf")
    indexer.update_player_stats({"Curry": {"season": {"Points": 25}}}, "2026-27")
    indexer.update_schedule(GAMES, "2026-27")
    indexer.update_rules("/x/rules.pdf")  # the old bug: this wiped stats and schedule
    assert _all(memory_store, "general_stats") and _all(memory_store, "general_schedule")


def test_schedule_is_grouped_by_date(indexer, memory_store):
    indexer.update_schedule(GAMES, "2026-27")
    [result] = _all(memory_store, "general_schedule")
    assert result.chunk.source == "NBA_schedule_2026-27.json"
    assert "Lakers" in result.chunk.text and "Knicks" in result.chunk.text


def test_unchanged_content_is_not_re_embedded(indexer, counting):
    report = {"Curry": {"season": {"Points": 25}}}
    assert indexer.update_player_stats(report, "2026-27") is True
    calls = counting.calls
    assert indexer.update_player_stats(report, "2026-27") is False
    assert counting.calls == calls
    assert indexer.update_player_stats({"Curry": {"season": {"Points": 26}}}, "2026-27") is True


def test_legacy_general_collection_can_be_dropped(indexer, memory_store):
    memory_store.replace_collection("general", [])
    assert memory_store.last_synced("general") is not None
    indexer.drop_legacy_general()
    assert memory_store.last_synced("general") is None
