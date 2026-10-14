import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from yahoo_fantasy_api.league import yfa
from .league_sync_manager import get_sync_manager
from .yahoo_tokens import TokenRefreshError, ensure_fresh, save_entry
from ....ingest.season import current_season, yahoo_game_year
from ....fantasy_integrations.yahoo.sync_league.sync_yahoo_league import YahooLeague
from ....storage.blob_storage import build_blob_storage
from ....repository.firestore import YahooLeagueRepository
from ....ai.document_indexer import DocumentIndexer

logger = logging.getLogger(__name__)

# (user guid, season year) -> (fetched at, league keys); the dashboard asks on every visit
_season_league_ids: dict[tuple[str, int], tuple[float, set[str]]] = {}
SEASON_LEAGUES_CACHE_SECONDS = 10 * 60


class YahooService:
    def __init__(self, token_store, document_indexer: DocumentIndexer):
        self.token_store = token_store
        # Get global sync manager with 15-minute TTL
        self.sync_manager = get_sync_manager(ttl_minutes=15)
        self.document_indexer = document_indexer

    def get_user_leagues(self, user_guid):
        """Get user's leagues from Yahoo API"""
        try:

            yahoo_game = get_yahoo_sdk(self.token_store, {"user": user_guid})
            if not yahoo_game:
                return []

            league_ids = yahoo_game.league_ids(year=yahoo_game_year(current_season()))
            league_options = []
            for league_id in league_ids:
                league = yahoo_game.to_league(league_id)
                league_name = league.settings()["name"]
                league_options.append({"id": league_id, "name": league_name})
            return league_options
        except Exception as e:
            logger.error(f"Error getting user leagues: {e}")
            return []

    def sync_league_data_async(
        self, league_id: str, user_guid: str, azure_container: str = "fantasy1"
    ):
        """
        Trigger non-blocking sync of league data to Azure.
        Uses background thread to avoid blocking the HTTP request.

        Args:
            league_id: League identifier
            user_guid: User GUID from session
            azure_container: Azure container name
        """
        thread = threading.Thread(
            target=self._sync_league_data_background,
            args=(league_id, user_guid, azure_container),
            daemon=True,  # Thread dies when main program exits
        )
        thread.start()
        logger.info(f"League {league_id}: Background sync thread started")

    def _sync_league_data_background(
        self, league_id: str, user_guid: str, azure_container: str
    ):
        """
        Background worker for syncing league data.
        Wraps sync_league_data() with error handling.
        """
        try:
            result = self.sync_league_data(league_id, user_guid, azure_container)
            if result.get("success"):
                logger.info(
                    f"League {league_id}: Background sync completed successfully"
                )
            else:
                logger.warning(
                    f"League {league_id}: Background sync completed with issues: {result}"
                )
        except Exception as e:
            logger.error(
                f"League {league_id}: Background sync failed with exception: {e}",
                exc_info=True,
            )

    def sync_league_data(
        self, league_id: str, user_guid: str, azure_container: str = "fantasy1"
    ) -> Dict[str, Any]:
        """
        Sync league data to Azure with TTL checking, locking, and smart updates.

        Process:
        1. Check if sync needed (TTL)
        2. Acquire lock (prevent concurrent syncs)
        3. Fetch Yahoo data and upload to Azure
        4. Update last_blob_sync only if critical blobs succeeded
        5. Release lock

        Args:
            league_id: League identifier
            user_guid: User GUID from session
            azure_container: Azure container name

        Returns:
            Dict with keys:
            - success (bool): Overall success status
            - message (str): Description of what happened
            - sync_results (Dict[str, bool]): Per-blob upload results
            - last_sync (str): ISO timestamp of last successful sync
        """
        yahoo_league_repo = YahooLeagueRepository()

        try:
            yahoo_game = get_yahoo_sdk(self.token_store, {"user": user_guid})
            if not yahoo_game:
                return {"success": False, "error": "Yahoo SDK not available", "db_message": "No database update - Yahoo SDK not available"}
            yahoo_user_id = self.token_store[user_guid].get(
                "xoauth_yahoo_guid"
            ) or self.token_store[user_guid].get("guid")

            # Step 1: link this user to the league, always. The league's AI index is shared,
            # but access to it (and "which team is mine") is per user, so a fresh index
            # synced by a league-mate must not stop this user's row from being written.
            league = yahoo_game.to_league(league_id)
            league_name = league.settings().get("name", "Unknown League")
            user_data = league.teams()[league.team_key()]
            league_data = {
                "yahoo_user_id": yahoo_user_id,
                "league_id": league_id,
                "team_name": user_data.get("name", "Unknown Team"),
                "league_name": league_name,
                "team_id": user_data.get("team_id", ""),
            }
            if yahoo_league_repo.league_exist_for_user(league_id, yahoo_user_id):
                yahoo_league_repo.update_by_league_id_and_yahoo_user_id(league_id, yahoo_user_id, league_data)
                db_message = "League updated in database"
            else:
                league_data["created_at"] = datetime.now(timezone.utc).isoformat()
                yahoo_league_repo.create(league_data)
                db_message = "League added to database"

            # Step 2: skip the heavy sync while the league's index is fresh (TTL)
            last_blob_sync = _parse_ts((yahoo_league_repo.get_by_league_id(league_id) or {}).get("last_blob_sync"))
            if not self.sync_manager.should_sync(league_id, last_blob_sync):
                return {
                    "success": True,
                    "message": "Data is fresh, sync skipped",
                    "db_message": db_message,
                    "last_sync": last_blob_sync.isoformat() if last_blob_sync else None,
                    "skipped": True,
                }

            # Step 3: one sync per league at a time
            if not self.sync_manager.try_acquire_sync_lock(league_id):
                return {
                    "success": True,
                    "message": "Sync already in progress for this league",
                    "db_message": db_message,
                    "in_progress": True,
                }

            try:
                # Step 4: fetch and archive (GCS / Azure / none, see BLOB_STORAGE)
                yahoo_league = YahooLeague(league)
                sync_results = yahoo_league.sync_full_league(build_blob_storage(azure_container))

                if sync_results:
                    self.document_indexer.update_league_files(league_id, sync_results)

                # Step 5: the league only counts as fresh if its critical parts synced,
                # so a partial sync is retried on the next visit instead of in 15 minutes
                if yahoo_league.critical_ok:
                    yahoo_league_repo.update_by_league_id_and_yahoo_user_id(
                        league_id, yahoo_user_id, {"last_blob_sync": datetime.now(timezone.utc).isoformat()}
                    )

                logger.info(f"League {league_id}: Sync done, failed parts: {yahoo_league.failed or 'none'}")
                return {
                    "success": yahoo_league.critical_ok,
                    "message": f"Synced {len(sync_results)} parts"
                               + (f"; failed: {', '.join(yahoo_league.failed)}" if yahoo_league.failed else ""),
                    "db_message": db_message,
                    "failed": yahoo_league.failed,
                    "last_sync": datetime.now(timezone.utc).isoformat(),
                }

            finally:
                # Always release lock, even if exception occurs
                self.sync_manager.release_sync_lock(league_id)

        except Exception as e:
            logger.error(f"League {league_id}: Sync error: {e}", exc_info=True)
            return {"success": False, "error": str(e), "db_message": "No database update - sync failed with error"}

    def current_season_league_ids(self, user_guid) -> set[str]:
        """Keys of the user's Yahoo leagues this NBA season. Yahoo gives a league a new
        key every season, so last season's copy of a league is not in this set.
        Raises if Yahoo can't be reached."""
        year = yahoo_game_year(current_season())
        cache_key = (user_guid, year)
        cached = _season_league_ids.get(cache_key)
        if cached and time.monotonic() - cached[0] < SEASON_LEAGUES_CACHE_SECONDS:
            return cached[1]
        yahoo_game = get_yahoo_sdk(self.token_store, {"user": user_guid})
        if not yahoo_game:
            return set()
        ids = set(yahoo_game.league_ids(year=year))
        _season_league_ids[cache_key] = (time.monotonic(), ids)
        return ids

    def get_user_synced_leagues(self, user_guid):
        """The user's synced leagues for the current season. Leagues synced in earlier
        seasons stay stored but are not listed. Raises if the leagues can't be loaded,
        so the dashboard can say so instead of showing an empty list."""
        yahoo_user_id = self.token_store[user_guid].get(
            "xoauth_yahoo_guid"
        ) or self.token_store[user_guid].get("guid")
        if not yahoo_user_id:
            return []

        synced = YahooLeagueRepository().get_by_yahoo_user_id(yahoo_user_id)
        if not synced:
            return []
        this_season = self.current_season_league_ids(user_guid)
        return [row for row in synced if row.get("league_id") in this_season]


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class CustomYahooSession:
    def __init__(self, token_data):
        self.access_token = token_data["access_token"]
        self.refresh_token = token_data.get("refresh_token")
        self.token_type = token_data.get("token_type", "bearer")
        self.token = token_data
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})


def get_yahoo_sdk(token_store, session):
    """
    Returns an authenticated yahoo_fantasy_api.Game object for the current user session.
    Returns None if the user is not authenticated or token is missing.
    """
    user_guid = session.get("user")
    if not user_guid or user_guid not in token_store:
        return None
    entry = token_store[user_guid]
    try:
        refreshed = ensure_fresh(entry)
    except TokenRefreshError:
        # Access was revoked: forget it so the dashboard offers "Connect Yahoo" again
        token_store.pop(user_guid, None)
        _mark_flask_session_modified()
        raise
    if refreshed:
        if entry.get("guid"):
            save_entry(entry)
        _mark_flask_session_modified()
    sc = CustomYahooSession(entry)
    return yfa.Game(sc, "nba")


def _mark_flask_session_modified():
    """token_store lives in the Flask session cookie; nested edits aren't detected."""
    from flask import has_request_context, session as flask_session

    if has_request_context():
        flask_session.modified = True
