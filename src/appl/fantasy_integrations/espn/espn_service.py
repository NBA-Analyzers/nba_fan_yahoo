import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from . import espn_credentials
from .espn_league_info import my_team as _my_team
from .sync_league.sync_espn_league import EspnLeague
from ..yahoo.sync_league.league_sync_manager import get_sync_manager
from ...ai.document_indexer import DocumentIndexer
from ...ingest.season import current_season, season_start_year
from ...storage.blob_storage import build_blob_storage

logger = logging.getLogger(__name__)

ESPN_CHAT_PREFIX = "espn-"
LEAGUE_CACHE_SECONDS = 60  # pages poll often; opening a League costs several ESPN calls


def espn_chat_id(league_id: str) -> str:
    """The id the chat, the blobs and the RAG index use for an ESPN league. The prefix
    keeps it apart from Yahoo's numeric ids."""
    return f"{ESPN_CHAT_PREFIX}{league_id}"


def espn_id_from_chat(chat_league_id: Optional[str]) -> Optional[str]:
    if chat_league_id and chat_league_id.startswith(ESPN_CHAT_PREFIX):
        return chat_league_id[len(ESPN_CHAT_PREFIX):]
    return None


def espn_year(season: Optional[str] = None) -> int:
    """ESPN names a season by the year it ends: 2025-26 is 2026."""
    return season_start_year(season or current_season()) + 1


class EspnError(Exception):
    """A problem worth showing to the user as is (no secrets in the message)."""


def _open_league(league_id: int, year: int, espn_s2: Optional[str], swid: Optional[str]):
    from espn_api.basketball import League
    return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)


def _friendly(e: Exception) -> EspnError:
    name = type(e).__name__
    if name == "ESPNAccessDenied":
        return EspnError("ESPN refused access. The league is private: add your espn_s2 and SWID "
                         "cookies, or reconnect if they expired.")
    if name == "ESPNInvalidLeague":
        return EspnError("ESPN couldn't find that league id for that season.")
    return EspnError("We couldn't reach ESPN. Please try again in a moment.")


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class EspnService:
    def __init__(self, document_indexer: DocumentIndexer, league_repo=None, auth_repo=None,
                 open_league: Callable = _open_league):
        self.document_indexer = document_indexer
        self.sync_manager = get_sync_manager(ttl_minutes=15)
        self._league_repo = league_repo
        self._auth_repo = auth_repo
        self._open_league = open_league
        self._leagues: dict[tuple[str, str], tuple[float, Any, Optional[str]]] = {}
        self._leagues_lock = threading.Lock()

    # Repos are built on use so importing the service never needs the database
    @property
    def league_repo(self):
        if self._league_repo is None:
            from ...repository.firestore.espn_data import EspnLeagueRepository
            self._league_repo = EspnLeagueRepository()
        return self._league_repo

    @property
    def auth_repo(self):
        if self._auth_repo is None:
            from ...repository.firestore.espn_data import EspnAuthRepository
            self._auth_repo = EspnAuthRepository()
        return self._auth_repo

    # --- connect / disconnect ------------------------------------------------

    def connect(self, user_id: str, league_id: str, season_year: int,
                espn_s2: Optional[str] = None, swid: Optional[str] = None) -> Dict[str, Any]:
        """Check the league can be read, keep the cookies encrypted, link the league to the
        signed-in user. Raises EspnError with a message safe to show."""
        if not str(league_id).isdigit():
            raise EspnError("An ESPN league id is a number, as in the league's URL.")
        espn_s2, swid = (espn_s2 or "").strip() or None, (swid or "").strip() or None
        if bool(espn_s2) != bool(swid):
            raise EspnError("Private leagues need both cookies, espn_s2 and SWID.")
        if espn_s2:
            espn_credentials.encrypt("check")  # fail before touching ESPN if there is no key
        try:
            league = self._open_league(int(league_id), season_year, espn_s2, swid)
            name = getattr(league.settings, "name", None) or "ESPN league"
            mine = _my_team(league, swid)
        except Exception as e:
            logger.warning("ESPN league %s: connect failed: %s", league_id, type(e).__name__)
            raise _friendly(e)

        if espn_s2:
            self.auth_repo.save(user_id, espn_credentials.encrypt(espn_s2), espn_credentials.encrypt(swid))

        self.league_repo.save(user_id, str(league_id), {
            "league_name": name, "team_name": getattr(mine, "team_name", None) or "Your team",
            "team_id": str(getattr(mine, "team_id", "") or ""), "season_year": season_year,
            "connected_at": datetime.now(timezone.utc).isoformat()})
        return {"league_id": str(league_id), "league_name": name}

    def disconnect(self, user_id: str) -> None:
        """Forget the cookies and the leagues of this user."""
        self.auth_repo.delete_by_user_id(user_id)
        self.league_repo.delete_by_user_id(user_id)

    # --- sync ----------------------------------------------------------------

    def _cookies(self, user_id: str) -> tuple[Optional[str], Optional[str]]:
        row = self.auth_repo.get_by_user_id(user_id)
        if not row:
            return None, None
        return espn_credentials.decrypt(row["espn_s2_enc"]), espn_credentials.decrypt(row["swid_enc"])

    def sync_league_data_async(self, user_id: str, league_id: str, container: str = "fantasy1"):
        def run():
            try:
                result = self.sync_league_data(user_id, league_id, container)
                if not result.get("success"):
                    logger.warning("ESPN league %s: background sync issues: %s", league_id, result)
            except Exception as e:
                logger.error("ESPN league %s: background sync failed: %s", league_id, e, exc_info=True)

        threading.Thread(target=run, daemon=True).start()

    def sync_league_data(self, user_id: str, league_id: str, container: str = "fantasy1") -> Dict[str, Any]:
        """TTL check, per-league lock, fetch + archive + index, and last_blob_sync only when
        the critical parts synced (the same flow as YahooService.sync_league_data)."""
        row = self.league_repo.league_exist_for_user(league_id, user_id)
        if not row:
            return {"success": False, "error": "That ESPN league isn't connected to your account."}
        chat_id = espn_chat_id(league_id)

        last = _parse_ts(row.get("last_blob_sync"))
        if not self.sync_manager.should_sync(chat_id, last):
            return {"success": True, "message": "Data is fresh, sync skipped", "skipped": True,
                    "last_sync": last.isoformat() if last else None}
        if not self.sync_manager.try_acquire_sync_lock(chat_id):
            return {"success": True, "message": "Sync already in progress for this league", "in_progress": True}
        try:
            try:
                s2, swid = self._cookies(user_id)
                league = self._open_league(int(league_id), int(row.get("season_year") or espn_year()), s2, swid)
            except espn_credentials.CredentialsError as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": str(_friendly(e))}

            espn = EspnLeague(league, chat_id)
            results = espn.sync_full_league(build_blob_storage(container))
            if results:
                self.document_indexer.update_league_files(chat_id, results)
            if espn.critical_ok:
                self.league_repo.save(
                    user_id, league_id, {"last_blob_sync": datetime.now(timezone.utc).isoformat()})
            return {
                "success": espn.critical_ok,
                "message": f"Synced {len(results)} parts"
                           + (f"; failed: {', '.join(espn.failed)}" if espn.failed else ""),
                "failed": espn.failed,
                "last_sync": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error("ESPN league %s: sync error: %s", league_id, e, exc_info=True)
            return {"success": False, "error": "The sync failed. Please try again in a moment."}
        finally:
            self.sync_manager.release_sync_lock(chat_id)

    def load_league(self, user_id: str, league_id: str, now=time.monotonic):
        """The live espn_api League of one of the user's connected leagues, plus their SWID
        (it finds their team). Cached for a minute. Raises KeyError for a league that is
        not theirs, EspnError / CredentialsError when it can't be read."""
        if not self.league_repo.league_exist_for_user(league_id, user_id):
            raise KeyError(league_id)
        key = (user_id, league_id)
        with self._leagues_lock:
            cached = self._leagues.get(key)
            if cached and now() - cached[0] < LEAGUE_CACHE_SECONDS:
                return cached[1], cached[2]
        row = self.league_repo.league_exist_for_user(league_id, user_id)
        s2, swid = self._cookies(user_id)
        try:
            league = self._open_league(int(league_id), int(row.get("season_year") or espn_year()), s2, swid)
        except Exception as e:
            raise _friendly(e)
        with self._leagues_lock:
            self._leagues[key] = (now(), league, swid)
        return league, swid

    def get_user_leagues(self, user_id: str) -> list:
        try:
            return self.league_repo.get_by_user_id(user_id) or []
        except Exception as e:
            logger.error("Error retrieving ESPN leagues: %s", e)
            return []
