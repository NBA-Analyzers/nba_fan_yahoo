"""
Personal access tokens, so tools like Claude Code can act for a Google user
without a browser session (e.g. importing a league from screenshots).

A token is shown once when it is made; only its SHA-256 is stored, so a leaked
store doesn't leak working tokens. Same storage choice as manual leagues:
Firestore on Cloud Run, a JSON file everywhere else.
"""

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "api_tokens.json"
PREFIX = "fbh_"
MAX_TOKENS_PER_USER = 10
_lock = threading.RLock()


def _digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FileTokenBackend:
    """digest -> record, in one JSON file. Fine for local development."""

    def __init__(self, path: Path = DATA_FILE):
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get(self, digest: str) -> dict | None:
        return self._load().get(digest)

    def put(self, digest: str, record: dict) -> None:
        with _lock:
            data = self._load()
            data[digest] = record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)

    def delete(self, digest: str) -> None:
        with _lock:
            data = self._load()
            if data.pop(digest, None) is not None:
                self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def for_user(self, user: str) -> list[tuple[str, dict]]:
        return [(d, r) for d, r in self._load().items() if r.get("user") == user]


class FirestoreTokenBackend:
    """Layout: <root>/<digest> -> {"user", "label", "created", "hint"}."""

    def __init__(self, client=None, root: str = "api_tokens"):
        self._client_obj = client
        self.root = root

    def _col(self):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj.collection(self.root)

    def get(self, digest: str) -> dict | None:
        snap = self._col().document(digest).get()
        return snap.to_dict() if snap.exists else None

    def put(self, digest: str, record: dict) -> None:
        self._col().document(digest).set(record)

    def delete(self, digest: str) -> None:
        self._col().document(digest).delete()

    def for_user(self, user: str) -> list[tuple[str, dict]]:
        return [(s.id, s.to_dict()) for s in self._col().where("user", "==", user).stream()]


class ApiTokenStore:
    def __init__(self, backend=None):
        self.backend = backend or FileTokenBackend()

    def create(self, user: str, label: str = "") -> str:
        """A new token for `user`. Returned once; only its hash is kept."""
        if len(self.backend.for_user(user)) >= MAX_TOKENS_PER_USER:
            raise ValueError(f"You already have {MAX_TOKENS_PER_USER} tokens; revoke one first")
        token = PREFIX + secrets.token_urlsafe(32)
        self.backend.put(_digest(token), {
            "user": user,
            "label": (str(label or "").strip() or "Claude Code")[:40],
            "created": _now(),
            "hint": token[-4:],
        })
        return token

    def user_for(self, token: str | None) -> str | None:
        """The user a token belongs to, or None if it is unknown or revoked."""
        if not token or not token.startswith(PREFIX):
            return None
        record = self.backend.get(_digest(token))
        return record.get("user") if record else None

    def list(self, user: str) -> list[dict]:
        """The user's tokens, without the secrets. `id` is the hash, for revoking."""
        rows = [{"id": d, **{k: r.get(k) for k in ("label", "created", "hint")}} for d, r in self.backend.for_user(user)]
        return sorted(rows, key=lambda r: r["created"] or "", reverse=True)

    def revoke(self, user: str, token_id: str) -> bool:
        record = self.backend.get(token_id)
        if not record or record.get("user") != user:
            return False
        self.backend.delete(token_id)
        return True


def default_token_store() -> ApiTokenStore:
    """Follows MANUAL_LEAGUE_STORE / K_SERVICE like the league store."""
    kind = os.environ.get("MANUAL_LEAGUE_STORE") or ("firestore" if os.environ.get("K_SERVICE") else "file")
    return ApiTokenStore(FirestoreTokenBackend() if kind == "firestore" else None)
