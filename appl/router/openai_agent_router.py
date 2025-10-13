from flask import Blueprint, request
from model.chat import AssistantResponse
from service.openai_agent_manager import OpenaiAgentManager


class OpenaiAgentRouter:
    def __init__(self, openai_agent_manager: OpenaiAgentManager):
        self.openai_agent_manager = openai_agent_manager
        self._blueprint = self._create_blueprint()

    def _create_blueprint(self):
        openai_agent_bp = Blueprint("openai_agent", __name__)

        @openai_agent_bp.route("/chat", methods=["POST"])
        async def chat() -> AssistantResponse:
            chat_request = request.get_json()
            assistant_response = await self.openai_agent_manager.chat(chat_request)
            return assistant_response.output_text

        return openai_agent_bp

    def get_bp(self):
        return self._blueprint
