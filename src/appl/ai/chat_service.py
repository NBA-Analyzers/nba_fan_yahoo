import json
import logging
import os
from datetime import date
from typing import Callable, Iterator, Optional

from ..model.file import GENERAL_COLLECTIONS
from ..model.vector_store import generate_league_vector_store_id
from ..service.chat_session_manager import ChatSessionManager
from .ports import LLMClient, LLMReply
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

    def _prepare(self, chat_request: dict):
        """Validate the request and build the messages. Returns (session_id, user_message,
        messages, toolkit)."""
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
        return session_id, user_message, messages, toolkit

    def _remember(self, session_id: str, user_message: str, answer: str) -> None:
        self.sessions.add_messages(session_id, [("user", user_message), ("assistant", answer)])

    def chat(self, chat_request: dict) -> str:
        session_id, user_message, messages, toolkit = self._prepare(chat_request)
        answer = self._answer_with_tools(messages, toolkit) if toolkit is not None else self.llm.complete(messages)
        self._remember(session_id, user_message, answer)
        return answer

    def chat_stream(self, chat_request: dict) -> Iterator[str]:
        """Same as `chat`, but yields the answer in pieces as the model writes it. The
        request is validated now, so a bad one raises here and not on the first piece."""
        session_id, user_message, messages, toolkit = self._prepare(chat_request)
        return self._stream(session_id, user_message, messages, toolkit)

    def _stream(self, session_id: str, user_message: str, messages: list[dict], toolkit) -> Iterator[str]:
        tools = toolkit.specs if toolkit is not None else None
        sent: list[str] = []
        for _ in range(MAX_TOOL_ROUNDS if toolkit is not None else 1):
            reply: Optional[LLMReply] = None
            wrote = False
            for item in self.llm.stream_turn(messages, tools):
                if isinstance(item, LLMReply):
                    reply = item
                else:
                    wrote = True
                    sent.append(item)
                    yield item
            if reply is None or not reply.tool_calls:
                break
            if wrote:  # text written before calling tools: keep it apart from what follows
                sent.append("\n\n")
                yield "\n\n"
            self._run_tools(messages, reply, toolkit)
        else:
            # Out of rounds: make the model answer with what it has
            messages.append({"role": "system", "content": "Answer now using the tool results above."})
            for item in self.llm.stream_turn(messages, None):
                if not isinstance(item, LLMReply):
                    sent.append(item)
                    yield item
        self._remember(session_id, user_message, "".join(sent).strip())

    def _run_tools(self, messages: list[dict], reply: LLMReply, toolkit) -> None:
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

    def _answer_with_tools(self, messages: list[dict], toolkit) -> str:
        """Let the model call the toolkit until it answers (at most MAX_TOOL_ROUNDS rounds)."""
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.llm.complete_with_tools(messages, toolkit.specs)
            if not reply.tool_calls:
                return reply.content
            self._run_tools(messages, reply, toolkit)
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
