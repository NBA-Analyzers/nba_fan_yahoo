from flask import Blueprint, jsonify, request

from ..ai.access import Access
from ..ai.document_indexer import DocumentIndexer


class DocumentRouter:
    """Re-index a league's files. The shared rules/stats index is refreshed by
    `python -m appl.ingest run general_index`, not over HTTP."""

    def __init__(self, document_indexer: DocumentIndexer, access: Access):
        self.document_indexer = document_indexer
        self.access = access
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        document_bp = Blueprint("documents", __name__)

        @document_bp.route("/<league_id>/update_files", methods=["POST"])
        def update_league_files(league_id: str):
            user = self.access.current_user()
            if user is None:
                return jsonify({"error": "Not logged in"}), 401
            if not self.access.can_access_league(user, league_id):
                return jsonify({"error": "No access to this league"}), 403
            files = request.get_json(silent=True)
            if not isinstance(files, dict) or not files:
                return jsonify({"error": "Expected a JSON object of files"}), 400
            collection_id = self.document_indexer.update_league_files(league_id, files)
            return jsonify({"collection_id": collection_id})

        return document_bp

    def get_bp(self):
        return self._blueprint
