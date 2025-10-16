import os
from pathlib import Path

from common.repository.supaBase.models.vector_store import generate_league_vector_store_id
from model.chat import ChatRequest

from openai import OpenAI
from openai.types.responses import Response
from service.chat_session_manager import ChatSessionManager
from common.vector_store_manager import VectorStoreManager


class OpenaiAgentManager:
    def __init__(
        self,
        chat_session_manager: ChatSessionManager,
        vector_store_manager: VectorStoreManager,
        openai_client: OpenAI,
    ):
        self.chat_session_manager = chat_session_manager
        self.vector_store_manager = vector_store_manager
        self.openai_client = openai_client

    async def chat(self, chat_request: ChatRequest) -> Response:
        chat_session = self.chat_session_manager.get_existing_or_create(
            chat_request["session_id"]
        )
        assistant_response = self.start_chat_with_openai(
            previous_response_id=chat_session.previous_openai_response_id,
            new_user_message=chat_request["user_message"],
            league_id=chat_request["league_id"],
        )
        self.chat_session_manager.update_chat_session(
            chat_session.session_id, assistant_response.id
        )

        return assistant_response

    def start_chat_with_openai(
        self, previous_response_id: str, new_user_message: str, league_id: str
    ) -> Response:
        tools = self.create_tools(league_id)
        instructions = self.get_instructions()

        return self.openai_client.responses.create(
            model="gpt-4.1-mini",
            instructions=instructions,
            input=new_user_message,
            previous_response_id=previous_response_id,
            tools=tools,
        )

    def create_tools(self, league_id: str):
        openai_league_vs_id = self.vector_store_manager.get_vector_store_by_id(
            generate_league_vector_store_id(league_id)
        ).openai_vector_id

        # openai_box_score_vs_id = self.vector_store_manager.get_vector_store_by_id(
        #     VectorStorePurpose.BOX_SCORE
        # )
        # openai_rules_vs_id = self.vector_store_manager.get_vector_store_by_id(
        #     VectorStorePurpose.RULES
        # )

        return [
            {
                "type": "file_search",
                "vector_store_ids": [
                    openai_league_vs_id,
                    # openai_box_score_vs_id,
                    # openai_rules_vs_id,
                ],
            }
        ]

    def get_instructions(self):
        instructions_path = Path(os.environ["SYSTEM_PROMPT_PATH"])
        return instructions_path.read_text(encoding="utf-8")
