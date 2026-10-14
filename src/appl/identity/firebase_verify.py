"""Verify a Firebase ID token on the server (firebase-admin, Application Default Credentials)."""
import os

_app = None


class InvalidToken(Exception):
    pass


def verify_id_token(token: str) -> dict:
    """The decoded claims of a valid, unexpired Firebase ID token. Raises InvalidToken."""
    global _app
    import firebase_admin
    from firebase_admin import auth

    if _app is None:
        _app = firebase_admin.initialize_app(
            options={"projectId": os.environ.get("FIREBASE_PROJECT_ID")
                     or os.environ.get("GOOGLE_CLOUD_PROJECT")})
    try:
        return auth.verify_id_token(token, app=_app)
    except Exception as exc:  # expired, malformed, wrong project, revoked, ...
        raise InvalidToken(type(exc).__name__) from exc
