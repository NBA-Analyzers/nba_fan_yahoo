"""Server-side sessions: the cookie holds only a random id, the data stays on the server.

Backends (SESSION_STORE=firestore|memory, default firestore when K_SERVICE is set, i.e.
on Cloud Run, memory everywhere else and in tests):
  - Firestore, collection `web_sessions`: the document id is the SHA-256 of the session
    id (a leaked database doesn't hand out live cookies). Fields: data, created_at,
    expires_at (a timestamp for a Firestore TTL policy), user_key.
  - Memory: thread-safe, with expiry. Lost on restart.

Lifetime is sliding (SESSION_LIFETIME_DAYS, default 30). A session that is never
touched (health checks, the homepage) creates no record and no cookie.
"""
import hashlib
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from flask.json.tag import TaggedJSONSerializer
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict

COLLECTION = "web_sessions"
COOKIE_NAME = "fbh_sid"
TOUCH_EVERY = timedelta(hours=12)  # push the expiry forward at most this often
_serializer = TaggedJSONSerializer()


def session_doc_id(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


class SessionStore(Protocol):
    def load(self, sid: str, now: datetime) -> Optional[dict]: ...

    def save(self, sid: str, data: dict, expires_at: datetime, created_at: Optional[datetime]) -> None: ...

    def delete(self, sid: str) -> None: ...


class MemorySessionStore:
    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._lock = threading.RLock()

    def load(self, sid, now):
        with self._lock:
            row = self._rows.get(session_doc_id(sid))
            if row is None:
                return None
            if row["expires_at"] <= now:
                del self._rows[session_doc_id(sid)]
                return None
            return {"data": _serializer.loads(row["data"]), "created_at": row["created_at"],
                    "expires_at": row["expires_at"]}

    def save(self, sid, data, expires_at, created_at):
        with self._lock:
            self._rows[session_doc_id(sid)] = {
                "data": _serializer.dumps(dict(data)),
                "created_at": created_at or datetime.now(timezone.utc),
                "expires_at": expires_at,
                "user_key": data.get("user_id"),
            }

    def delete(self, sid):
        with self._lock:
            self._rows.pop(session_doc_id(sid), None)

    def __len__(self):
        return len(self._rows)


class FirestoreSessionStore:
    """The client is created on first use, so building the store needs no credentials."""

    def __init__(self, client=None):
        self._client_obj = client

    def _ref(self, sid):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj.collection(COLLECTION).document(session_doc_id(sid))

    def load(self, sid, now):
        snap = self._ref(sid).get()
        if not snap.exists:
            return None
        row = snap.to_dict()
        if row["expires_at"] <= now:
            return None  # the TTL policy removes the document later
        return {"data": _serializer.loads(row["data"]), "created_at": row.get("created_at"),
                "expires_at": row["expires_at"]}

    def save(self, sid, data, expires_at, created_at):
        self._ref(sid).set({
            "data": _serializer.dumps(dict(data)),
            "created_at": created_at or datetime.now(timezone.utc),
            "expires_at": expires_at,
            "user_key": data.get("user_id"),
        })

    def delete(self, sid):
        self._ref(sid).delete()


class ServerSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid: Optional[str] = None, created_at=None, expires_at=None):
        def on_update(self):
            self.modified = True
            self.accessed = True

        super().__init__(initial, on_update)
        self.sid, self.created_at, self.expires_at = sid, created_at, expires_at
        self.modified = False
        self.accessed = False
        self.rotate_pending = False

    def __getitem__(self, key):
        self.accessed = True
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.accessed = True
        return super().get(key, default)

    def setdefault(self, key, default=None):
        self.accessed = True
        return super().setdefault(key, default)

    def rotate(self):
        """Issue a new session id at the end of this request (after login: stops fixation).
        The data is kept, the old record is deleted."""
        self.rotate_pending = True
        self.modified = True


class ServerSessionInterface(SessionInterface):
    def __init__(self, store: SessionStore, lifetime: timedelta, cookie_name: str = COOKIE_NAME):
        self.store, self.lifetime, self.cookie_name = store, lifetime, cookie_name

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def open_session(self, app, request):
        sid = request.cookies.get(self.cookie_name)
        if sid:
            row = self.store.load(sid, self._now())
            if row is not None:
                return ServerSession(row["data"], sid, row["created_at"], row["expires_at"])
        return ServerSession()  # unknown or expired id: a fresh, empty session

    def save_session(self, app, session, response):
        domain, path = self.get_cookie_domain(app), self.get_cookie_path(app)
        secure, samesite = self.get_cookie_secure(app), self.get_cookie_samesite(app)
        httponly = self.get_cookie_httponly(app)

        def drop_cookie():
            response.delete_cookie(self.cookie_name, domain=domain, path=path, secure=secure,
                                   samesite=samesite, httponly=httponly)

        if session.accessed:
            response.vary.add("Cookie")
        if session.sid and not session.modified:
            # sliding expiry, written at most every TOUCH_EVERY
            now = self._now()
            if session.expires_at and session.expires_at - now < self.lifetime - TOUCH_EVERY:
                self.store.save(session.sid, session, now + self.lifetime, session.created_at)
                self._set_cookie(response, session.sid, now + self.lifetime, domain, path,
                                 secure, samesite, httponly)
            return
        if not session.modified:
            return  # anonymous and untouched: no record, no cookie
        if not session:  # cleared (logout) or emptied
            if session.sid:
                self.store.delete(session.sid)
            drop_cookie()
            return

        sid, created_at = session.sid, session.created_at
        if sid and session.rotate_pending:
            self.store.delete(sid)
            sid = None
        if not sid:
            sid = secrets.token_urlsafe(32)
            created_at = created_at if session.rotate_pending else None
        expires_at = self._now() + self.lifetime
        self.store.save(sid, session, expires_at, created_at)
        self._set_cookie(response, sid, expires_at, domain, path, secure, samesite, httponly)

    def _set_cookie(self, response, sid, expires_at, domain, path, secure, samesite, httponly):
        response.set_cookie(self.cookie_name, sid, expires=expires_at, httponly=httponly,
                            domain=domain, path=path, secure=secure, samesite=samesite)


def default_store_kind() -> str:
    return os.environ.get("SESSION_STORE") or ("firestore" if os.environ.get("K_SERVICE") else "memory")


def build_session_interface(kind: Optional[str] = None, firestore_client=None) -> ServerSessionInterface:
    kind = kind or default_store_kind()
    store = FirestoreSessionStore(firestore_client) if kind == "firestore" else MemorySessionStore()
    days = float(os.environ.get("SESSION_LIFETIME_DAYS") or 30)
    return ServerSessionInterface(store, timedelta(days=days))
