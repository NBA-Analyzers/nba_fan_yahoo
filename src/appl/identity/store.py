"""Users and the sign-in identities linked to them.

A user is an opaque `user_id`. An identity is one way of signing in
(`google.com` + Google sub, `password` + Firebase uid, ...). Several identities
can point at one user.
"""
import os
from datetime import datetime, timezone
from typing import Optional, Protocol

from ..draft.manual_league import user_hash


def identity_key(provider: str, provider_user_id: str) -> str:
    return f"{provider}:{provider_user_id}"


class IdentityStore(Protocol):
    def get_identity(self, provider: str, provider_user_id: str) -> Optional[dict]: ...

    def find_by_verified_email(self, email: str) -> Optional[dict]: ...

    def put_identity(self, provider: str, provider_user_id: str, user_id: str,
                     email: str, email_verified: bool) -> None: ...

    def upsert_user(self, user_id: str, profile: dict) -> None: ...


class MemoryIdentityStore:
    def __init__(self):
        self.identities: dict[str, dict] = {}
        self.users: dict[str, dict] = {}

    def get_identity(self, provider, provider_user_id):
        return self.identities.get(identity_key(provider, provider_user_id))

    def find_by_verified_email(self, email):
        for doc in self.identities.values():
            if doc["email_verified"] and doc["email"] == email:
                return doc
        return None

    def put_identity(self, provider, provider_user_id, user_id, email, email_verified):
        self.identities.setdefault(identity_key(provider, provider_user_id), {
            "user_id": user_id, "provider": provider, "email": email,
            "email_verified": email_verified,
        })

    def upsert_user(self, user_id, profile):
        self.users.setdefault(user_id, {}).update(profile)


class FirestoreIdentityStore:
    """`users/<user_hash>` and `identities/<user_hash of "provider:id">`. The client
    is created on first use, so building the store needs no credentials."""

    def __init__(self, client=None):
        self._client_obj = client

    def _client(self):
        if self._client_obj is None:
            from google.cloud import firestore

            self._client_obj = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        return self._client_obj

    def _identity_ref(self, provider, provider_user_id):
        return self._client().collection("identities").document(
            user_hash(identity_key(provider, provider_user_id)))

    def get_identity(self, provider, provider_user_id):
        snap = self._identity_ref(provider, provider_user_id).get()
        return snap.to_dict() if snap.exists else None

    def find_by_verified_email(self, email):
        query = (self._client().collection("identities")
                 .where("email", "==", email).where("email_verified", "==", True).limit(1))
        for snap in query.stream():
            return snap.to_dict()
        return None

    def put_identity(self, provider, provider_user_id, user_id, email, email_verified):
        """Create-if-absent: if another login got there first, its user_id stands."""
        from google.api_core.exceptions import AlreadyExists

        try:
            self._identity_ref(provider, provider_user_id).create({
                "user_id": user_id, "provider": provider, "email": email,
                "email_verified": email_verified,
            })
        except AlreadyExists:
            pass

    def upsert_user(self, user_id, profile):
        self._client().collection("users").document(user_hash(user_id)).set({
            "user_id": user_id,
            "full_name": profile.get("name", ""),
            "email": profile.get("email", ""),
            "picture": profile.get("picture", ""),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }, merge=True)
