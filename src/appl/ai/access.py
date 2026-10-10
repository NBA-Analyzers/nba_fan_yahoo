from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from flask import session


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    yahoo_id: Optional[str] = None


class Access(Protocol):
    def current_user(self) -> Optional[CurrentUser]: ...

    def can_access_league(self, user: CurrentUser, league_id: str) -> bool: ...


class SessionAccess:
    """Who is calling /chat and which leagues they may ask about.

    - identity: the signed-in user stored in the Flask session (`user_id`)
    - leagues: a Yahoo league is yours only if the yahoo_leagues collection links it to the
      Yahoo account of this session (rows are created when the league is synced); a
      manual league ("manual-<id>") is yours if it is stored under your user id; an ESPN
      league ("espn-<id>") is yours if the espn_leagues collection links it to your user id
    """

    def __init__(self, league_repo_factory: Callable[[], object], manual_store=None,
                 espn_repo_factory: Optional[Callable[[], object]] = None):
        self._league_repo_factory = league_repo_factory
        self._manual_store = manual_store
        self._espn_repo_factory = espn_repo_factory

    def current_user(self) -> Optional[CurrentUser]:
        user_id = session.get("user_id")
        if not user_id:
            return None
        return CurrentUser(user_id=user_id, yahoo_id=session.get("user"))

    def can_access_league(self, user: CurrentUser, league_id: str) -> bool:
        from ..fantasy_integrations.espn.espn_service import espn_id_from_chat
        from ..season.service import manual_id_from_chat

        espn_id = espn_id_from_chat(league_id)
        if espn_id is not None:
            # An ESPN league is yours only if it was connected under your user id
            if self._espn_repo_factory is None:
                return False
            return bool(self._espn_repo_factory().league_exist_for_user(espn_id, user.user_id))
        manual_id = manual_id_from_chat(league_id)
        if manual_id is not None:
            if self._manual_store is None:
                return False
            try:
                self._manual_store.get(user.user_id, manual_id)
            except KeyError:
                return False
            return True
        if not user.yahoo_id:
            return False
        repo = self._league_repo_factory()
        return bool(repo.league_exist_for_user(league_id, user.yahoo_id))
