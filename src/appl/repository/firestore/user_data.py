"""Users, Yahoo logins, fantasy-platform links and Yahoo leagues, in Firestore.

Layout (all server-side only; the Firestore rules deny every client):
  users/<user_hash>                       a signed-in user (Google sub or our own user_id)
  yahoo_auth/<yahoo guid>                 Yahoo OAuth tokens, SECRETS, never logged
  fantasy_connections/<hash>_<platform>_<fantasy user id>
                                          which user is linked to which fantasy account
  yahoo_leagues/<league id>_<yahoo guid>  leagues synced for a Yahoo account

Every write uses a deterministic document id and set(merge=True), so two
simultaneous logins or a reconnect land on the same document and are idempotent.
The "created" time is the document's own create_time, so it is never overwritten.

The public methods keep the names of the old Supabase services.
"""
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ...draft.manual_league import user_hash

logger = logging.getLogger(__name__)

PLATFORMS = ("yahoo", "espn")


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def retry_once(fn: Callable, what: str = "storage call"):
    """Run `fn`; on any error log it and try one more time (transient errors)."""
    try:
        return fn()
    except Exception:
        logger.warning("%s failed, retrying once", what, exc_info=True)  # storage errors only
        time.sleep(0.2)
        return fn()


def _check_id(value: str, label: str) -> str:
    if not value or not str(value).strip():
        raise ValidationError(f"{label} cannot be empty")
    if "/" in str(value):
        raise ValidationError(f"{label} is not a valid id")
    return str(value)


def _check_platform(platform: str) -> str:
    if not platform or platform.lower() not in PLATFORMS:
        raise ValidationError(f"Invalid platform '{platform}'. Allowed: {', '.join(PLATFORMS)}")
    return platform.lower()


@dataclass
class GoogleAuth:
    google_user_id: str
    full_name: str
    email: str
    access_token: Optional[str] = None  # a secret: stored server-side, never logged
    created_at: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class YahooAuth:
    yahoo_user_id: str
    access_token: str
    refresh_token: str
    username: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class GoogleFantasy:
    google_user_id: str
    fantasy_user_id: str
    fantasy_platform: str
    created_at: Optional[str] = None


class FirestoreClient:
    """Shared lazy client, so building a service needs no credentials."""

    def __init__(self, client=None):
        self._client_obj = client

    def client(self):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj

    def col(self, name: str):
        return self.client().collection(name)


def _created(snap, data: dict) -> Optional[str]:
    if data.get("created_at"):
        return data["created_at"]
    created = getattr(snap, "create_time", None)
    return created.isoformat() if created else None


class AuthService:
    def __init__(self, client=None):
        self.fs = client if isinstance(client, FirestoreClient) else FirestoreClient(client)

    # Users (was google_auth)
    def create_or_update_google_user(self, google_auth: GoogleAuth) -> GoogleAuth:
        """One idempotent write; safe if two logins arrive together."""
        user_id = _check_id(google_auth.google_user_id, "User ID")
        payload = {
            "user_id": user_id,
            "full_name": google_auth.full_name,
            "email": (google_auth.email or "").lower(),
            "last_updated": _now(),
        }
        if google_auth.access_token:
            payload["access_token"] = google_auth.access_token
        ref = self.fs.col("users").document(user_hash(user_id))
        ref.set(payload, merge=True)
        return GoogleAuth(user_id, payload["full_name"], payload["email"],
                          last_updated=payload["last_updated"])

    def save_google_token(self, user_id: str, access_token: str) -> None:
        """Keep the Google access token with the user record (a secret, never logged)."""
        self.fs.col("users").document(user_hash(_check_id(user_id, "User ID"))).set(
            {"user_id": user_id, "access_token": access_token, "last_updated": _now()}, merge=True)

    def get_google_user(self, google_user_id: str) -> GoogleAuth:
        snap = self.fs.col("users").document(user_hash(google_user_id)).get()
        if not snap.exists:
            raise NotFoundError(f"User {google_user_id} not found")
        d = snap.to_dict()
        return GoogleAuth(d["user_id"], d.get("full_name", ""), d.get("email", ""),
                          created_at=_created(snap, d), last_updated=d.get("last_updated"))

    # Yahoo logins (tokens are secrets: never log them)
    def create_or_update_yahoo_user(self, yahoo_auth: YahooAuth) -> YahooAuth:
        guid = _check_id(yahoo_auth.yahoo_user_id, "Yahoo user ID")
        payload = {
            "yahoo_user_id": guid,
            "access_token": yahoo_auth.access_token,
            "refresh_token": yahoo_auth.refresh_token,
            "last_updated": _now(),
        }
        if yahoo_auth.username:
            payload["username"] = yahoo_auth.username
        self.fs.col("yahoo_auth").document(guid).set(payload, merge=True)
        return YahooAuth(guid, yahoo_auth.access_token, yahoo_auth.refresh_token,
                         payload.get("username"), last_updated=payload["last_updated"])

    def get_yahoo_user(self, yahoo_user_id: str) -> YahooAuth:
        snap = self.fs.col("yahoo_auth").document(_check_id(yahoo_user_id, "Yahoo user ID")).get()
        if not snap.exists:
            raise NotFoundError(f"Yahoo user with id {yahoo_user_id} not found")
        d = snap.to_dict()
        return YahooAuth(d["yahoo_user_id"], d.get("access_token", ""), d.get("refresh_token", ""),
                         d.get("username"), _created(snap, d), d.get("last_updated"))

    def update_yahoo_tokens(self, yahoo_user_id: str, access_token: str,
                            refresh_token: str) -> None:
        ref = self.fs.col("yahoo_auth").document(_check_id(yahoo_user_id, "Yahoo user ID"))
        ref.update({"access_token": access_token, "refresh_token": refresh_token,
                    "last_updated": _now()})  # raises NotFound if the login was never saved


class FantasyService:
    def __init__(self, client=None):
        self.fs = client if isinstance(client, FirestoreClient) else FirestoreClient(client)

    @staticmethod
    def _id(user_id: str, platform: str, fantasy_user_id: str) -> str:
        return f"{user_hash(user_id)}_{platform}_{fantasy_user_id}"

    def connect_fantasy_platform(self, google_fantasy: GoogleFantasy) -> GoogleFantasy:
        """Link a user to a fantasy account. Idempotent: a reconnect succeeds silently."""
        user_id = _check_id(google_fantasy.google_user_id, "User ID")
        fantasy_id = _check_id(google_fantasy.fantasy_user_id, "Fantasy user ID")
        platform = _check_platform(google_fantasy.fantasy_platform)
        if platform == "yahoo":
            if not self.fs.col("yahoo_auth").document(fantasy_id).get().exists:
                raise ValidationError(f"Yahoo user '{fantasy_id}' does not exist")
        self.fs.col("fantasy_connections").document(self._id(user_id, platform, fantasy_id)).set({
            "google_user_id": user_id,
            "fantasy_user_id": fantasy_id,
            "fantasy_platform": platform,
            "last_connected": _now(),
        }, merge=True)
        return GoogleFantasy(user_id, fantasy_id, platform)

    def get_user_fantasy_connections(self, google_user_id: str) -> List[GoogleFantasy]:
        user_id = _check_id(google_user_id, "User ID")
        snaps = self.fs.col("fantasy_connections").where("google_user_id", "==", user_id).stream()
        out = [GoogleFantasy(d["google_user_id"], d["fantasy_user_id"], d["fantasy_platform"],
                             _created(s, d)) for s in snaps for d in [s.to_dict()]]
        return sorted(out, key=lambda c: (c.fantasy_platform, c.fantasy_user_id))

    def get_fantasy_connection(self, google_user_id: str, platform: str) -> Optional[GoogleFantasy]:
        platform = _check_platform(platform)
        for conn in self.get_user_fantasy_connections(google_user_id):
            if conn.fantasy_platform == platform:
                return conn
        return None

    def get_yahoo_user_id_for_google_user(self, google_user_id: str) -> Optional[str]:
        """The authorization path for restoring a saved Yahoo login: only a link
        written for THIS user id is returned."""
        conn = self.get_fantasy_connection(google_user_id, "yahoo")
        return conn.fantasy_user_id if conn else None

    def get_all_yahoo_user_ids_for_google_user(self, google_user_id: str) -> List[str]:
        return [c.fantasy_user_id for c in self.get_user_fantasy_connections(google_user_id)
                if c.fantasy_platform == "yahoo"]

    def disconnect_specific_fantasy_connection(self, google_user_id: str, fantasy_user_id: str,
                                               platform: str) -> bool:
        platform = _check_platform(platform)
        ref = self.fs.col("fantasy_connections").document(
            self._id(_check_id(google_user_id, "User ID"), platform,
                     _check_id(fantasy_user_id, "Fantasy user ID")))
        if not ref.get().exists:
            raise NotFoundError("This specific connection does not exist")
        ref.delete()
        return True


class YahooLeagueRepository:
    def __init__(self, client=None):
        self.fs = client if isinstance(client, FirestoreClient) else FirestoreClient(client)

    @staticmethod
    def _id(league_id: str, yahoo_user_id: str) -> str:
        return f"{_check_id(league_id, 'League ID')}_{_check_id(yahoo_user_id, 'Yahoo user ID')}"

    def _col(self):
        return self.fs.col("yahoo_leagues")

    def get_by_yahoo_user_id(self, yahoo_user_id: str) -> List[Dict[str, Any]]:
        return [s.to_dict() | {"created_at": _created(s, s.to_dict())}
                for s in self._col().where("yahoo_user_id", "==", yahoo_user_id).stream()]

    def get_by_league_id(self, league_id: str) -> Optional[Dict[str, Any]]:
        for snap in self._col().where("league_id", "==", league_id).limit(1).stream():
            return snap.to_dict()
        return None

    def league_exist_for_user(self, league_id: str, yahoo_user_id: str) -> Optional[Dict[str, Any]]:
        """The league-access check: true only for a league linked to THIS Yahoo account."""
        if not league_id or not yahoo_user_id:
            return None
        snap = self._col().document(self._id(league_id, yahoo_user_id)).get()
        return snap.to_dict() if snap.exists else None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._col().document(self._id(data["league_id"], data["yahoo_user_id"])).set(
            data, merge=True)
        return data

    def update_by_league_id_and_yahoo_user_id(self, league_id: str, yahoo_user_id: str,
                                              data: Dict[str, Any]) -> Dict[str, Any]:
        self._col().document(self._id(league_id, yahoo_user_id)).set(data, merge=True)
        return data

    def delete_by_yahoo_user_id(self, yahoo_user_id: str) -> bool:
        deleted = False
        for snap in self._col().where("yahoo_user_id", "==", yahoo_user_id).stream():
            snap.reference.delete()
            deleted = True
        return deleted
