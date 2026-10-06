from flask import Blueprint, jsonify, request

from .litellm_adapters import LLMError


class ChatRouter:
    def __init__(self, chat_service):
        self.chat_service = chat_service
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        chat_bp = Blueprint("chat", __name__)

        @chat_bp.route("/chat", methods=["POST"])
        def chat():
            chat_request = request.get_json(silent=True)
            if not isinstance(chat_request, dict):
                return jsonify(error="JSON body required"), 400
            try:
                return self.chat_service.chat(chat_request)
            except ValueError as e:
                return jsonify(error=str(e)), 400
            except LLMError:
                return jsonify(error="The AI service is unavailable, please try again"), 502

        return chat_bp

    def get_bp(self):
        return self._blueprint
