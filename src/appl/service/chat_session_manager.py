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

    def append(self, session_id: str, messages: list[dict]) -> None:
        """Add messages after whatever is stored now, atomically."""
        ...


class FirestoreChatSessionStore:
    """Conversations in Firestore, so they survive restarts and are shared by every Cloud Run
    instance. Appends run in a transaction, so turns saved at the same moment by two
    instances are both kept. Documents expire after SESSION_DAYS via a TTL policy on `expires_at`:
    gcloud firestore fields ttls update expires_at --collection-group=chat_sessions --enable-ttl"""

    COLLECTION = "chat_sessions"

    def __init__(self, client, days: int = SESSION_DAYS, now=lambda: datetime.now(timezone.utc),
                 collection: str = COLLECTION, transactional=None):
        self._client = client
        self._days = days
        self._now = now
        self._collection = collection
        self._transactional = transactional

    @staticmethod
    def _doc_id(session_id: str) -> str:
        # Session ids hold a user id and a client-chosen string; hash them into a safe document id
        return hashlib.sha256(session_id.encode()).hexdigest()

    def _ref(self, session_id: str):
        return self._client.collection(self._collection).document(self._doc_id(session_id))

    def load(self, session_id: str) -> Optional[list[dict]]:
        snap = self._ref(session_id).get()
        if not snap.exists:
            return None
        return list((snap.to_dict() or {}).get("messages") or [])

    def append(self, session_id: str, messages: list[dict]) -> None:
        """Read, add, trim and write in one transaction. Firestore re-runs the body when the
        document changed under it, so the body only builds on the snapshot it is given."""
        transactional = self._transactional
        if transactional is None:
            from google.cloud import firestore

            transactional = firestore.transactional
        ref = self._ref(session_id)

        def run(transaction):
            snap = ref.get(transaction=transaction)
            stored = list((snap.to_dict() or {}).get("messages") or []) if snap.exists else []
            now = self._now()
            transaction.set(ref, {
                "messages": (stored + list(messages))[-MAX_STORED_MESSAGES:],
                "updated_at": now,
                "expires_at": now + timedelta(days=self._days),
            })

        transactional(run)(self._client.transaction())


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
    fallback for when the store can't be read. New messages are appended to the store, never
    written over it, so neither a failed read nor a stale copy can lose saved messages."""

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

    def _find(self, session_id: str) -> Optional[ChatSession]:
        if self.store is not None:
            try:
                messages = self.store.load(session_id)
            except Exception as e:
                logger.warning("Chat session load failed: %s", type(e).__name__)
                messages = None
            if messages is not None:
                loaded = ChatSession(session_id=session_id, messages=messages)
                self._remember(loaded)
                return loaded
        return self._from_memory(session_id)

    def get_existing_or_create(self, session_id: str) -> ChatSession:
        chat_session = self._find(session_id)
        if chat_session is None:
            chat_session = ChatSession(session_id=session_id)
            self.add_chat_session(chat_session)
        return chat_session

    def add_chat_session(self, chat_session: ChatSession):
        self._remember(chat_session)

    def add_messages(self, session_id: str, messages: list[tuple[str, str]]) -> None:
        """Append (role, content) pairs: to the memory copy, and to the store in one write."""
        new = [{"role": role, "content": content} for role, content in messages]
        session = self._from_memory(session_id)
        if session is None:
            session = ChatSession(session_id=session_id)
            self.add_chat_session(session)
        session.messages.extend(dict(m) for m in new)
        if self.store is None:
            return
        try:
            self.store.append(session_id, new)
        except Exception as e:
            logger.warning("Chat session save failed: %s", type(e).__name__)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.add_messages(session_id, [(role, content)])

    def history(self, session_id: str, max_turns: int | None = None) -> list[dict]:
        session = self._find(session_id)
        if session is None:
            return []
        messages = session.messages
        if max_turns is not None:
            messages = messages[-2 * max_turns :] if max_turns > 0 else []
        return [dict(m) for m in messages]
