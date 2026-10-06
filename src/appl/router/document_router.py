from typing import Dict

from flask import Blueprint, request
from ..ai.document_indexer import DocumentIndexer


class DocumentRouter:
    def __init__(self, document_indexer: DocumentIndexer):
        self.document_indexer = document_indexer
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        document_bp = Blueprint("documents", __name__)

        @document_bp.route("/<league_id>/update_files", methods=["POST"])
        def update_league_files(league_id: str):
            # TODO: validate all league files are in the list
            files = request.get_json()
            self.document_indexer.update_league_files(league_id, files)

        @document_bp.route("/update_rules", methods=["POST"])
        def update_rules(file: Dict[str, str]):
            file = request.get_json()
            self.document_indexer.update_rules(file)

        return document_bp

    def get_bp(self):
        return self._blueprint
