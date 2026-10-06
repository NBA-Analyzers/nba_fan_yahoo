import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..model.file import FilePurpose
from ..model.vector_store import generate_league_vector_store_id
from .pdf import extract_pdf_text
from .retrieval import Document, RetrievalService


class DocumentIndexer:
    """Replaces OpenaiFileManager: same public methods, but indexes into our own store."""

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

    def update_rules(self, pdf_path: str) -> str:
        collection_id = FilePurpose.GENERAL.value
        self.retrieval.index(collection_id, [self._pdf_document(pdf_path)])
        return collection_id

    def update_player_stats(
        self,
        json_path: str,
        pdf_path: Optional[str] = None,
        schedule_path: Optional[str] = None,
    ) -> str:
        documents = [self._json_document(json_path)]
        if pdf_path:
            documents.append(self._pdf_document(pdf_path))
        if schedule_path:
            documents.append(self._json_document(schedule_path))
        collection_id = FilePurpose.GENERAL.value
        self.retrieval.index(collection_id, documents)
        return collection_id

    def _pdf_document(self, path: str) -> Document:
        return Document(source=Path(path).name, text=self.pdf_extractor(path))

    @staticmethod
    def _json_document(path: str) -> Document:
        with open(path, encoding="utf-8") as f:
            return Document(source=Path(path).name, data=json.load(f))
