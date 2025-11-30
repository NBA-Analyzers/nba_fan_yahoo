import logging
import os
from pathlib import Path

from ..model.chat import ChatRequest
from ..model.file import FilePurpose
from ..model.vector_store import generate_league_vector_store_id
from openai import OpenAI
from openai.types.responses import Response
from .chat_session_manager import ChatSessionManager
from .vector_store_manager import VectorStoreManager


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

        if tools is None:
            # Create a custom Response object with all required fields
            tools = []

        instructions = self.get_instructions()

        return self.openai_client.responses.create(
            model="gpt-4.1-mini",
            instructions=instructions,
            input=new_user_message,
            previous_response_id=previous_response_id,
            tools=tools,
        )

    def create_tools(self, league_id: str):
        openai_league_vs = self.vector_store_manager.get_vector_store_by_id(
            generate_league_vector_store_id(league_id)
        )

        if openai_league_vs is None:
            return None

        vector_store_ids = [openai_league_vs.openai_vector_id]

        openai_rules_vs = self.vector_store_manager.get_vector_store_by_id(
            FilePurpose.GENERAL.value
        )

        if openai_rules_vs is None:
            logging.error("No rules vector store found")
        else:
            vector_store_ids.append(openai_rules_vs.openai_vector_id)

        return [
            {
                "type": "file_search",
                "vector_store_ids": vector_store_ids,
            }
        ]

    def get_instructions(self):
        # Uri did it because he had a problem with the system prompt

        default_prompt_path = (
            Path(__file__).resolve().parent.parent / "utils" / "system_prompt.md"
        )
        env_prompt_path = os.environ.get("SYSTEM_PROMPT_PATH")

        instructions_path = (
            Path(env_prompt_path).expanduser()
            if env_prompt_path is not None
            else default_prompt_path
        )
        return instructions_path.read_text(encoding="utf-8")
