import hashlib
import logging
import os
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from ..model.chat import ChatSession

logger = logging.getLogger(__name__)

MAX_MEMORY_SESSIONS = 500  # least recently used sessions are dropped from memory (not from the store)
MAX_STORED_MESSAGES = 60  # a stored conversation keeps its latest messages only
SESSION_DAYS = 30


class ChatSessionStore(Protocol):
    def load(self, session_id: str) -> Optional[list[dict]]: ...

    def save(self, session_id: str, messages: list[dict]) -> None: ...


class FirestoreChatSessionStore:
    """Conversations in Firestore, so they survive restarts and are shared by every Cloud Run
    instance. Documents expire after SESSION_DAYS via a TTL policy on `expires_at`:
    gcloud firestore fields ttls update expires_at --collection-group=chat_sessions --enable-ttl"""

    COLLECTION = "chat_sessions"

    def __init__(self, client, days: int = SESSION_DAYS, now=lambda: datetime.now(timezone.utc)):
        self._client = client
        self._days = days
        self._now = now

    @staticmethod
    def _doc_id(session_id: str) -> str:
        # Session ids hold a user id and a client-chosen string; hash them into a safe document id
        return hashlib.sha256(session_id.encode()).hexdigest()

    def load(self, session_id: str) -> Optional[list[dict]]:
        snap = self._client.collection(self.COLLECTION).document(self._doc_id(session_id)).get()
        if not snap.exists:
            return None
        return list((snap.to_dict() or {}).get("messages") or [])

    def save(self, session_id: str, messages: list[dict]) -> None:
        now = self._now()
        self._client.collection(self.COLLECTION).document(self._doc_id(session_id)).set({
            "messages": messages[-MAX_STORED_MESSAGES:],
            "updated_at": now,
            "expires_at": now + timedelta(days=self._days),
        })


def default_store() -> Optional[ChatSessionStore]:
    """Firestore on Cloud Run (which sets K_SERVICE), memory only elsewhere.
    Override with CHAT_SESSION_STORE=firestore or =memory."""
    kind = os.environ.get("CHAT_SESSION_STORE") or ("firestore" if os.environ.get("K_SERVICE") else "memory")
    if kind != "firestore":
        return None
    from google.cloud import firestore

    return FirestoreChatSessionStore(firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT")))


class ChatSessionManager:
    """Conversation history per session. With a store, every read goes to the store (another
    Cloud Run instance may have added to the conversation) and the memory copy is only a
    fallback for when the store can't be read. A conversation is never saved after a failed
    read, so one timeout can't overwrite the stored history with a partial copy."""

    def __init__(self, store: Optional[ChatSessionStore] = None, max_memory: int = MAX_MEMORY_SESSIONS):
        self.store = store
        self.max_memory = max_memory
        self.chat_sessions: "OrderedDict[str, ChatSession]" = OrderedDict()

    def _remember(self, chat_session: ChatSession) -> None:
        self.chat_sessions[chat_session.session_id] = chat_session
        self.chat_sessions.move_to_end(chat_session.session_id)
        while len(self.chat_sessions) > self.max_memory:
            self.chat_sessions.popitem(last=False)

    def _from_memory(self, session_id: str) -> Optional[ChatSession]:
        found = self.chat_sessions.get(session_id)
        if found is not None:
            self.chat_sessions.move_to_end(session_id)
        return found

    def _find(self, session_id: str) -> tuple[Optional[ChatSession], bool]:
        """(the session or None, whether it is safe to save over the stored copy)."""
        if self.store is None:
            return self._from_memory(session_id), True
        try:
            messages = self.store.load(session_id)
        except Exception as e:
            logger.warning("Chat session load failed: %s", type(e).__name__)
            return self._from_memory(session_id), False
        if messages is None:
            return self._from_memory(session_id), True
        loaded = ChatSession(session_id=session_id, messages=messages)
        self._remember(loaded)
        return loaded, True

    def get_existing_or_create(self, session_id: str) -> ChatSession:
        chat_session = self._find(session_id)[0]
        if chat_session is None:
            chat_session = ChatSession(session_id=session_id)
            self.add_chat_session(chat_session)
        return chat_session

    def add_chat_session(self, chat_session: ChatSession):
        self._remember(chat_session)

    def add_messages(self, session_id: str, messages: list[tuple[str, str]]) -> None:
        """Append (role, content) pairs, with one read and one write to the store."""
        session, can_save = self._find(session_id)
        if session is None:
            session = ChatSession(session_id=session_id)
            self.add_chat_session(session)
        session.messages.extend({"role": role, "content": content} for role, content in messages)
        if self.store is None:
            return
        if not can_save:
            logger.warning("Chat session not saved: its stored history could not be read")
            return
        try:
            self.store.save(session_id, session.messages)
        except Exception as e:
            logger.warning("Chat session save failed: %s", type(e).__name__)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.add_messages(session_id, [(role, content)])

    def history(self, session_id: str, max_turns: int | None = None) -> list[dict]:
        session = self._find(session_id)[0]
        if session is None:
            return []
        messages = session.messages
        if max_turns is not None:
            messages = messages[-2 * max_turns :] if max_turns > 0 else []
        return [dict(m) for m in messages]
