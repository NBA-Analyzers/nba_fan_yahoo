import json
import logging

from flask import Blueprint, Response, jsonify, request, stream_with_context

from .access import Access
from .litellm_adapters import LLMError

logger = logging.getLogger(__name__)


class ChatRouter:
    def __init__(self, chat_service, access: Access):
        self.chat_service = chat_service
        self.access = access
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        chat_bp = Blueprint("chat", __name__)

        @chat_bp.route("/chat", methods=["POST"])
        def chat():
            user = self.access.current_user()
            if user is None:
                return jsonify(error="Please log in first"), 401

            chat_request = request.get_json(silent=True)
            if not isinstance(chat_request, dict):
                return jsonify(error="JSON body required"), 400

            league_id = chat_request.get("league_id")
            league_id = league_id.strip() if isinstance(league_id, str) else None
            league_id = league_id or None

            if league_id is not None:
                try:
                    allowed = self.access.can_access_league(user, league_id)
                except Exception:
                    logger.exception("League access check failed")
                    return jsonify(error="Could not verify league access, try again"), 503
                if not allowed:
                    return (
                        jsonify(
                            error="This league is not linked to your account "
                            "(if you just connected it, wait a few seconds for the sync)"
                        ),
                        403,
                    )

            request_for_service = dict(chat_request)
            request_for_service["league_id"] = league_id
            request_for_service["user_id"] = user.user_id  # set here, never trusted from the client
            # Keep every user's chat history separate, whatever session_id the client sends
            client_session_id = chat_request.get("session_id")
            if client_session_id:
                request_for_service["session_id"] = f"{user.user_id}:{client_session_id}"

            try:
                if chat_request.get("stream") is True:
                    return self._stream_response(request_for_service)
                return self.chat_service.chat(request_for_service)
            except ValueError as e:
                return jsonify(error=str(e)), 400
            except LLMError:
                return jsonify(error="The AI service is unavailable, please try again"), 502

        return chat_bp

    def _stream_response(self, request_for_service: dict) -> Response:
        """The answer as it is written: one JSON object per line, {"delta": text} pieces and
        a closing {"done": true}, or {"error": message} if the model fails part-way (the
        status is already sent by then). A bad request still gets its 400 first."""
        pieces = self.chat_service.chat_stream(request_for_service)

        def lines():
            try:
                for piece in pieces:
                    yield json.dumps({"delta": piece}) + "\n"
                yield json.dumps({"done": True}) + "\n"
            except LLMError:
                yield json.dumps({"error": "The AI service is unavailable, please try again"}) + "\n"
            except Exception:
                logger.exception("Chat stream failed")
                yield json.dumps({"error": "Something went wrong. Please try again."}) + "\n"

        return Response(stream_with_context(lines()), mimetype="application/x-ndjson",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def get_bp(self):
        return self._blueprint
