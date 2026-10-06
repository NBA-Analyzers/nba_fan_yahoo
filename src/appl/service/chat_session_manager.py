from typing import Dict
from ..model.chat import ChatSession


class ChatSessionManager:

    def __init__(self):
        self.chat_sessions: Dict[str, ChatSession] = {}

    def get_existing_or_create(self, session_id: str) -> ChatSession:
        chat_session = self.chat_sessions.get(session_id)
        if chat_session is None:
            chat_session = ChatSession(session_id=session_id)
            self.add_chat_session(chat_session)
        return chat_session

    def add_chat_session(self, chat_session: ChatSession):
        self.chat_sessions[chat_session.session_id] = chat_session

    def add_message(self, session_id: str, role: str, content: str) -> None:
        session = self.get_existing_or_create(session_id)
        session.messages.append({"role": role, "content": content})

    def history(self, session_id: str, max_turns: int | None = None) -> list[dict]:
        session = self.chat_sessions.get(session_id)
        if session is None:
            return []
        messages = session.messages
        if max_turns is not None:
            messages = messages[-2 * max_turns :] if max_turns > 0 else []
        return [dict(m) for m in messages]
