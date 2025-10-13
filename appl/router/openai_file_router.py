from typing import Dict

from flask import Blueprint, request
from service.openai_file_manager import OpenaiFileManager


class OpenaiFilesRouter:
    def __init__(self, openai_file_manager: OpenaiFileManager):
        self.openai_file_manager = openai_file_manager
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        openai_file_bp = Blueprint("openai_file", __name__)

        @openai_file_bp.route("/<league_id>/update_files", methods=["POST"])
        def update_league_files(league_id: str):
            # TODO: validate all league files are in the list
            files = request.get_json()
            self.openai_file_manager.update_league_files(league_id, files)

        @openai_file_bp.route("/update_box_score", methods=["POST"])
        def update_box_score():
            files = request.get_json()
            self.openai_file_manager.update_box_score(files)

        @openai_file_bp.route("/update_rules", methods=["POST"])
        def update_rules(file: Dict[str, str]):
            file = request.get_json()
            self.openai_file_manager.update_rules(file)

        return openai_file_bp

    def get_bp(self):
        return self._blueprint
