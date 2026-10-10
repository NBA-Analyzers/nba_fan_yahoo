"""Yahoo access tokens last an hour. Refresh one shortly before it expires so a long
session (or a sync started at minute 59) doesn't fail with 401s."""

import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
REFRESH_MARGIN_SECONDS = 120


class TokenRefreshError(RuntimeError):
    pass


def ensure_fresh(entry: dict, now: Optional[float] = None,
                 post: Optional[Callable] = None) -> bool:
    """Refresh `entry` (a token_store value) in place if it is about to expire.
    Returns True when it was refreshed."""
    now = time.time() if now is None else now
    expires_at = entry.get("expires_at")
    if expires_at is None or now < float(expires_at) - REFRESH_MARGIN_SECONDS:
        return False
    if not entry.get("refresh_token"):
        raise TokenRefreshError("Yahoo token expired and there is no refresh token")

    client_id = os.getenv("YAHOO_CLIENT_ID") or os.getenv("YAHOO_FANTASY_CLIENT_ID")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET") or os.getenv("YAHOO_FANTASY_CLIENT_SECRET")
    if post is None:
        import requests

        post = requests.post
    response = post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
            "redirect_uri": os.getenv("YAHOO_REDIRECT_URL") or "oob",
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise TokenRefreshError(f"Yahoo token refresh failed (HTTP {response.status_code})")
    token = response.json()
    entry["access_token"] = token["access_token"]
    entry["refresh_token"] = token.get("refresh_token", entry["refresh_token"])
    entry["expires_at"] = now + float(token.get("expires_in", 3600))
    logger.info("Yahoo token refreshed")
    return True


# The refresh token doesn't expire (only revoking access or a password change kills it), so
# Firestore yahoo_auth keeps the connection alive across logouts and browsers.

def load_saved_entry(user_id: str, fantasy=None, auth=None) -> Optional[dict]:
    """A token_store entry rebuilt from Firestore for this user, or None."""
    if fantasy is None or auth is None:
        from ....repository.firestore import AuthService, FantasyService

        fantasy, auth = fantasy or FantasyService(), auth or AuthService()
    yahoo_user_id = fantasy.get_yahoo_user_id_for_google_user(user_id)
    if not yahoo_user_id:
        return None
    saved = auth.get_yahoo_user(yahoo_user_id)
    if not saved.refresh_token:
        return None
    return {
        "access_token": saved.access_token,
        "refresh_token": saved.refresh_token,
        "expires_at": 0,  # the expiry isn't stored, so refresh on first use
        "guid": yahoo_user_id,
        "username": saved.username,
    }


def save_entry(entry: dict, auth=None) -> None:
    """Write refreshed tokens back so the next session starts from them."""
    try:
        if auth is None:
            from ....repository.firestore import AuthService

            auth = AuthService()
        auth.update_yahoo_tokens(entry["guid"], entry["access_token"], entry["refresh_token"])
    except Exception as e:
        logger.warning(f"Could not save refreshed Yahoo tokens: {e}")
