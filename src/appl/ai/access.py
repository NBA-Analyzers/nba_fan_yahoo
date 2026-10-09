from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from flask import session


@dataclass(frozen=True)
class CurrentUser:
    google_id: str
    yahoo_id: Optional[str] = None


class Access(Protocol):
    def current_user(self) -> Optional[CurrentUser]: ...

    def can_access_league(self, user: CurrentUser, league_id: str) -> bool: ...


class SessionAccess:
    """Who is calling /chat and which leagues they may ask about.

    - identity: the Google login stored in the Flask session (`google_user.sub`)
    - leagues: a Yahoo league is yours only if the yahoo_league table links it to the
      Yahoo account of this session (rows are created when the league is synced); a
      manual league ("manual-<id>") is yours if it is stored under your Google login
    """

    def __init__(self, league_repo_factory: Callable[[], object], manual_store=None):
        self._league_repo_factory = league_repo_factory
        self._manual_store = manual_store

    def current_user(self) -> Optional[CurrentUser]:
        google = session.get("google_user") or {}
        google_id = google.get("sub")
        if not google_id:
            return None
        return CurrentUser(google_id=google_id, yahoo_id=session.get("user"))

    def can_access_league(self, user: CurrentUser, league_id: str) -> bool:
        from ..draft.manual_league import user_key
        from ..season.service import manual_id_from_chat

        manual_id = manual_id_from_chat(league_id)
        if manual_id is not None:
            if self._manual_store is None:
                return False
            try:
                self._manual_store.get(user_key({"sub": user.google_id}), manual_id)
            except KeyError:
                return False
            return True
        if not user.yahoo_id:
            return False
        repo = self._league_repo_factory()
        return bool(repo.league_exist_for_user(league_id, user.yahoo_id))
