import os
from typing import Optional

from ..model.file import GENERAL_COLLECTIONS
from ..model.vector_store import generate_league_vector_store_id
from ..service.chat_session_manager import ChatSessionManager
from .ports import LLMClient
from .retrieval import RetrievalService

DEFAULT_HISTORY_TURNS = 10


class ChatService:
    def __init__(
        self,
        llm: LLMClient,
        retrieval: RetrievalService,
        sessions: ChatSessionManager,
        system_prompt: str,
        history_turns: Optional[int] = None,
    ):
        self.llm = llm
        self.retrieval = retrieval
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.history_turns = history_turns or int(
            os.environ.get("CHAT_HISTORY_TURNS", DEFAULT_HISTORY_TURNS)
        )

    def chat(self, chat_request: dict) -> str:
        session_id = chat_request.get("session_id")
        user_message = chat_request.get("user_message")
        if not session_id or not user_message or not user_message.strip():
            raise ValueError("session_id and user_message are required")

        messages = [{"role": "system", "content": self.system_prompt}]
        context = self._context(user_message, chat_request.get("league_id"))
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(self.sessions.history(session_id, self.history_turns))
        messages.append({"role": "user", "content": user_message})

        answer = self.llm.complete(messages)

        self.sessions.add_message(session_id, "user", user_message)
        self.sessions.add_message(session_id, "assistant", answer)
        return answer

    def _context(self, query: str, league_id: Optional[str]) -> str:
        collections = list(GENERAL_COLLECTIONS)
        if league_id:
            collections.insert(0, generate_league_vector_store_id(league_id))
        results = self.retrieval.retrieve(query, collections)
        if not results:
            return ""
        parts = [f"[{r.chunk.source}]\n{r.chunk.text}" for r in results]
        return "Relevant context from the user's league data and the rules:\n\n" + "\n\n".join(parts)
