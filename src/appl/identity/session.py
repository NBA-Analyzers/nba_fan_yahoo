"""The signed-in user, as stored in the Flask session by whichever login provider."""
from flask import abort, session


def current_user_id() -> str:
    """The id every per-user record is keyed by. Only call behind `require_login`."""
    user_id = session.get("user_id")
    if not user_id:
        abort(401)
    return user_id


def current_profile() -> dict:
    return session.get("profile") or {}


def rotate_session() -> None:
    """New session id, same data. Call after a login step succeeds (stops session
    fixation). A no-op for plain cookie sessions."""
    rotate = getattr(session, "rotate", None)
    if rotate:
        rotate()


def start_session(user_id: str, profile: dict) -> None:
    session["user_id"] = user_id
    session["profile"] = profile
    rotate_session()
