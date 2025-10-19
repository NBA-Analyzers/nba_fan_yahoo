from typing import Dict
from ..model.chat import ChatSession


class ChatSessionManager:

    def __init__(self):
        self.chat_sessions: Dict[str, ChatSession] = {}

    def get_existing_or_create(self, session_id: str) -> ChatSession:
        chat_session = self.chat_sessions.get(session_id)
        if chat_session is None:
            chat_session = ChatSession(
                session_id=session_id,
                previous_openai_response_id=None
            )
            self.add_chat_session(chat_session)
        return chat_session

    def add_chat_session(self, chat_session: ChatSession):
        self.chat_sessions[chat_session.session_id] = chat_session

    def update_chat_session(self, chat_session_id: str, previous_openai_response_id: str):
        chat_session = self.chat_sessions[chat_session_id]
        chat_session.previous_openai_response_id = previous_openai_response_id
        self.chat_sessions[chat_session.session_id] = chat_session
