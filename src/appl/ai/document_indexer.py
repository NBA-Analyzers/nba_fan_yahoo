from pathlib import Path
from typing import Any, Callable, Dict

from ..model.file import FilePurpose, GeneralCollection
from ..model.vector_store import generate_league_vector_store_id
from .pdf import extract_pdf_text
from .retrieval import Document, RetrievalService


class DocumentIndexer:
    """What goes into the AI index. Each shared source has its own collection, so
    re-indexing one (e.g. tonight's stats) never touches the others."""

    def __init__(
        self,
        retrieval: RetrievalService,
        pdf_extractor: Callable[[str], str] = extract_pdf_text,
    ):
        self.retrieval = retrieval
        self.pdf_extractor = pdf_extractor

    def update_league_files(self, league_id: str, files: Dict[str, Any]) -> str:
        collection_id = generate_league_vector_store_id(league_id)
        documents = [
            Document(source=f"{name}.json", data=content) for name, content in files.items()
        ]
        self.retrieval.index(collection_id, documents)
        return collection_id

    def update_rules(self, pdf_path: str) -> bool:
        """Index the rules PDF. False when its text hasn't changed (nothing re-embedded)."""
        doc = Document(source=Path(pdf_path).name, text=self.pdf_extractor(str(pdf_path)))
        return self.retrieval.index(GeneralCollection.RULES.value, [doc])

    def update_player_stats(self, report: Dict[str, Any], season: str) -> bool:
        doc = Document(source=f"player_stats_{season}.json", data=report)
        return self.retrieval.index(GeneralCollection.STATS.value, [doc])

    def update_schedule(self, games: list[dict], season: str) -> bool:
        """Games grouped by date, the shape the assistant was indexed with before."""
        by_date: Dict[str, list] = {}
        for g in games:
            by_date.setdefault(g["date"], []).append(
                {"home_team": g["home_team"], "away_team": g["away_team"], "game_id": g["game_id"]}
            )
        doc = Document(source=f"NBA_schedule_{season}.json", data=by_date)
        return self.retrieval.index(GeneralCollection.SCHEDULE.value, [doc])

    def drop_legacy_general(self) -> None:
        """The single shared collection used before the per-source split."""
        self.retrieval.store.delete_collection(FilePurpose.GENERAL.value)
