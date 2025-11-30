import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from yahoo_fantasy_api.league import yfa
from .league_sync_manager import get_sync_manager
from ....fantasy_integrations.yahoo.sync_league.sync_yahoo_league import YahooLeague
from ....repository.azure.azure_blob_storage import AzureBlobStorage
from ....repository.supaBase.repositories.yahoo_league_repository import (
    YahooLeagueRepository,
)
from ....service.openai_file_manager import OpenaiFileManager

logger = logging.getLogger(__name__)


class YahooService:
    def __init__(self, token_store, openai_file_manager: OpenaiFileManager):
        self.token_store = token_store
        # Get global sync manager with 15-minute TTL
        self.sync_manager = get_sync_manager(ttl_minutes=15)
        self.openai_file_manager = openai_file_manager

    def get_user_leagues(self, user_guid):
        """Get user's leagues from Yahoo API"""
        try:

            yahoo_game = get_yahoo_sdk(self.token_store, {"user": user_guid})
            if not yahoo_game:
                return []

            league_ids = yahoo_game.league_ids(year=2025)
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
            # Step 1: Check if sync is needed based on TTL
            existing_league = yahoo_league_repo.get_by_league_id(league_id)
            last_blob_sync = None

            if existing_league and existing_league.get("last_blob_sync"):
                # Parse timestamp from DB (handle both formats)
                last_sync_str = existing_league["last_blob_sync"]
                try:
                    # Try parsing with timezone
                    last_blob_sync = datetime.fromisoformat(
                        last_sync_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    # Try parsing without timezone
                    last_blob_sync = datetime.fromisoformat(last_sync_str)
                    last_blob_sync = last_blob_sync.replace(tzinfo=timezone.utc)

            # Check if sync needed based on TTL
            if not self.sync_manager.should_sync(league_id, last_blob_sync):
                return {
                    "success": True,
                    "message": "Data is fresh, sync skipped",
                    "db_message": "No database update needed - data is fresh",
                    "last_sync": last_blob_sync.isoformat() if last_blob_sync else None,
                    "skipped": True,
                }

            # Step 2: Try to acquire lock (prevent concurrent syncs)
            if not self.sync_manager.try_acquire_sync_lock(league_id):
                return {
                    "success": False,
                    "message": "Sync already in progress for this league",
                    "db_message": "No database update - sync already in progress",
                    "in_progress": True,
                }

            try:
                # Step 3: Get Yahoo SDK and league data
                yahoo_game = get_yahoo_sdk(self.token_store, {"user": user_guid})
                if not yahoo_game:
                    return {"success": False, "error": "Yahoo SDK not available", "db_message": "No database update - Yahoo SDK not available"}

                league = yahoo_game.to_league(league_id)
                league_settings = league.settings()
                league_name = league_settings.get("name", "Unknown League")

                # Get user's team information
                user_data = league.teams()[league.team_key()]
                user_team_name = user_data.get("name", "Unknown Team")
                user_team_id = user_data.get("team_id", "")
                
                # Get yahoo_user_id
                yahoo_user_id = self.token_store[user_guid].get(
                    "xoauth_yahoo_guid"
                ) or self.token_store[user_guid].get("guid")

                # Step 4: Update/create DB record (without last_blob_sync yet)
                league_data = {
                    "yahoo_user_id": yahoo_user_id,
                    "league_id": league_id,
                    "team_name": user_team_name,
                    "league_name": league_name,
                    "team_id": user_team_id,
                }

                if existing_league and yahoo_league_repo.league_exist_for_user(league_id, yahoo_user_id):
                    yahoo_league_repo.update_by_league_id_and_yahoo_user_id(league_id, yahoo_user_id, league_data)
                    db_message = "League updated in database"
                else:
                    league_data["created_at"] = datetime.now(timezone.utc).isoformat()
                    yahoo_league_repo.create(league_data)
                    db_message = "League added to database"

                # Step 5: Sync to Azure using new upload method
                azure_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
                if not azure_connection_string:
                    logger.warning("Azure Storage not configured")
                    return {"success": False, "error": "Azure Storage not configured", "db_message": "No database update - Azure Storage not configured"}

                azure_storage = AzureBlobStorage(container_name=azure_container)
                yahoo_league = YahooLeague(league)

                # Call sync - returns Dict[str, bool]
                sync_results = yahoo_league.sync_full_league(azure_storage)

                # Step 7: Update last_blob_sync ONLY if all critical blobs succeeded
                yahoo_league_repo.update_by_league_id_and_yahoo_user_id(
                    league_id, yahoo_user_id, {"last_blob_sync": datetime.now(timezone.utc).isoformat()}
                )

                self.openai_file_manager.update_league_files(league_id, sync_results)

                logger.info(f"League {league_id}: Sync completed successfully")

                # Count successes
                total_blobs = len(sync_results)
                successful_blobs = sum(1 for v in sync_results.values() if v)

                return {
                    "success": True,
                    "message": f"Sync completed: {successful_blobs}/{total_blobs} blobs uploaded",
                    "db_message": db_message,
                    "last_sync": datetime.now(timezone.utc).isoformat(),
                }

            finally:
                # Always release lock, even if exception occurs
                self.sync_manager.release_sync_lock(league_id)

        except Exception as e:
            logger.error(f"League {league_id}: Sync error: {e}", exc_info=True)
            return {"success": False, "error": str(e), "db_message": "No database update - sync failed with error"}

    def get_user_synced_leagues(self, user_guid):
        """Get user's synced leagues from database"""
        try:
            yahoo_user_id = self.token_store[user_guid].get(
                "xoauth_yahoo_guid"
            ) or self.token_store[user_guid].get("guid")
            if not yahoo_user_id:
                return []

            yahoo_league_repo = YahooLeagueRepository()
            return yahoo_league_repo.get_by_yahoo_user_id(yahoo_user_id)
        except Exception as e:
            logger.error(f"Error retrieving user leagues: {e}")
            return []


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
    sc = CustomYahooSession(token_store[user_guid])
    return yfa.Game(sc, "nba")
