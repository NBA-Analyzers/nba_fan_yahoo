"""Turn a verified sign-in (Firebase ID token claims, or Google userinfo) into our own `user_id`."""
import hashlib
import logging

from ..repository.firestore.user_data import retry_once
from .store import IdentityStore

logger = logging.getLogger(__name__)

GOOGLE = "google.com"


class UnverifiedEmail(Exception):
    """The sign-in has no verified email, so it can't be trusted to name or link a user."""


def email_user_id(email: str) -> str:
    """The user_id of a new email user: a hash of the verified email. Deterministic, so
    two first logins at once agree, and a storage outage can still name the user."""
    return "e_" + hashlib.sha256(email.encode()).hexdigest()[:24]


def _provider(claims: dict) -> tuple[str, str]:
    """(provider, provider user id). A Google sign-in is identified by the Google
    sub, which is not the Firebase uid, so old Google users keep their user_id."""
    firebase = claims.get("firebase") or {}
    google_ids = (firebase.get("identities") or {}).get(GOOGLE) or []
    if firebase.get("sign_in_provider") == GOOGLE and google_ids:
        return GOOGLE, str(google_ids[0])
    return firebase.get("sign_in_provider") or "password", claims["uid"]


def _profile(claims: dict, email: str) -> dict:
    return {
        "email": email,
        "name": claims.get("name") or email.split("@")[0],
        "given_name": claims.get("given_name") or "",
        "picture": claims.get("picture") or "",
    }


def resolve_user(store: IdentityStore, claims: dict) -> dict:
    """Return {"user_id", "profile"} for the claims of a verified sign-in.

    1. A known identity maps to its user.
    2. A new identity with a verified email that another identity already has joins
       that user (accounts are linked by verified email only).
    3. Otherwise a new user: the Google sub for Google, `email_user_id` for email.

    The identity write is create-if-absent on a deterministic document id and the id
    we return is read back, so two first logins at once agree on one user.
    The profile write is best effort: a failure is logged and does not block login.
    """
    email = (claims.get("email") or "").strip().lower()
    verified = bool(claims.get("email_verified"))
    if not email or not verified:
        raise UnverifiedEmail(email)
    provider, provider_id = _provider(claims)

    known = store.get_identity(provider, provider_id)
    if known:
        user_id = known["user_id"]
    else:
        match = store.find_by_verified_email(email)
        if match:
            user_id = match["user_id"]
        else:
            user_id = provider_id if provider == GOOGLE else email_user_id(email)
        store.put_identity(provider, provider_id, user_id, email, verified)
        user_id = store.get_identity(provider, provider_id)["user_id"]

    profile = _profile(claims, email)
    try:
        retry_once(lambda: store.upsert_user(user_id, profile), "user profile write")
    except Exception:
        logger.exception("Could not save the user record for %s; continuing the login", user_id)
    return {"user_id": user_id, "profile": profile}


def sign_in(store: IdentityStore, claims: dict) -> dict:
    """`resolve_user` with one retry on storage errors.

    A storage failure never blocks login: without the store the user is named by the
    id a new user would get (the Google sub, or `email_user_id`). The one catch is a
    user whose email was linked to an older account; during the outage they see the
    id-derived account, and the next login after recovery is correct again."""
    try:
        return retry_once(lambda: resolve_user(store, claims), "identity lookup")
    except (UnverifiedEmail, KeyError):
        raise
    except Exception as exc:
        provider, provider_id = _provider(claims)
        email = (claims.get("email") or "").strip().lower()
        logger.exception("Identity store unavailable; signing in %s user without it", provider)
        user_id = provider_id if provider == GOOGLE else email_user_id(email)
        return {"user_id": user_id, "profile": _profile(claims, email)}
