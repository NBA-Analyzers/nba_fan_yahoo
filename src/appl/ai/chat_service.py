import json
import logging
import os
from datetime import date
from typing import Callable, Optional

from ..model.file import GENERAL_COLLECTIONS
from ..model.vector_store import generate_league_vector_store_id
from ..service.chat_session_manager import ChatSessionManager
from .ports import LLMClient
from .retrieval import RetrievalService

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_TURNS = 10
MAX_TOOL_ROUNDS = 5


class ChatService:
    def __init__(
        self,
        llm: LLMClient,
        retrieval: RetrievalService,
        sessions: ChatSessionManager,
        system_prompt: str,
        history_turns: Optional[int] = None,
        tools_factory: Optional[Callable[[dict], object]] = None,
    ):
        """`tools_factory(chat_request)` returns a Toolkit for the league being asked
        about, or None when there is none (the chat then answers from retrieval alone)."""
        self.llm = llm
        self.retrieval = retrieval
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.tools_factory = tools_factory
        self.history_turns = history_turns or int(
            os.environ.get("CHAT_HISTORY_TURNS", DEFAULT_HISTORY_TURNS)
        )

    def chat(self, chat_request: dict) -> str:
        session_id = chat_request.get("session_id")
        user_message = chat_request.get("user_message")
        if not session_id or not user_message or not user_message.strip():
            raise ValueError("session_id and user_message are required")

        toolkit = self.tools_factory(chat_request) if self.tools_factory else None
        system = self.system_prompt
        if toolkit is not None:
            system += f"\n\nToday's date is {date.today().isoformat()}."
        messages = [{"role": "system", "content": system}]
        context = self._context(user_message, chat_request.get("league_id"))
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(self.sessions.history(session_id, self.history_turns))
        messages.append({"role": "user", "content": user_message})

        answer = self._answer_with_tools(messages, toolkit) if toolkit is not None else self.llm.complete(messages)

        self.sessions.add_message(session_id, "user", user_message)
        self.sessions.add_message(session_id, "assistant", answer)
        return answer

    def _answer_with_tools(self, messages: list[dict], toolkit) -> str:
        """Let the model call the toolkit until it answers (at most MAX_TOOL_ROUNDS rounds)."""
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.llm.complete_with_tools(messages, toolkit.specs)
            if not reply.tool_calls:
                return reply.content
            messages.append({
                "role": "assistant",
                "content": reply.content or None,
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": _json(c.arguments)}}
                    for c in reply.tool_calls
                ],
            })
            for call in reply.tool_calls:
                logger.info("Chat tool call: %s %s", call.name, call.arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": toolkit.call(call.name, call.arguments)})
        # Out of rounds: make the model answer with what it has
        messages.append({"role": "system", "content": "Answer now using the tool results above."})
        return self.llm.complete(messages)

    def _context(self, query: str, league_id: Optional[str]) -> str:
        collections = list(GENERAL_COLLECTIONS)
        if league_id:
            collections.insert(0, generate_league_vector_store_id(league_id))
        results = self.retrieval.retrieve(query, collections)
        if not results:
            return ""
        parts = [f"[{r.chunk.source}]\n{r.chunk.text}" for r in results]
        return "Relevant context from the user's league data and the rules:\n\n" + "\n\n".join(parts)


def _json(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"))
