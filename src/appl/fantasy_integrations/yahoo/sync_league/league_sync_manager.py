import threading
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LeagueSyncManager:
    """
    Manages per-league sync operations with debounce and locking.
    Prevents concurrent syncs for the same league and enforces TTL-based freshness.
    """

    def __init__(self, ttl_minutes: int = 15):
        """
        Args:
            ttl_minutes: Time-to-live in minutes before data is considered stale
        """
        self.ttl_minutes = ttl_minutes
        self._locks: Dict[str, threading.Lock] = {}
        self._last_sync_attempt: Dict[str, datetime] = {}
        self._global_lock = threading.Lock()

    def _get_league_lock(self, league_id: str) -> threading.Lock:
        """
        Get or create a lock for a specific league.
        Thread-safe lazy initialization.
        """
        with self._global_lock:
            if league_id not in self._locks:
                self._locks[league_id] = threading.Lock()
            return self._locks[league_id]

    def should_sync(self, league_id: str, last_blob_sync: Optional[datetime]) -> bool:
        """
        Determine if a league should be synced based on TTL and recent sync attempts.

        Args:
            league_id: League identifier
            last_blob_sync: Timestamp of last successful sync from database

        Returns:
            True if sync should proceed, False if data is still fresh
        """
        now = datetime.now(timezone.utc)

        # Check if data is stale based on last successful sync (from DB)
        if last_blob_sync:
            time_since_sync = now - last_blob_sync
            minutes_since_sync = time_since_sync.total_seconds() / 60

            if minutes_since_sync < self.ttl_minutes:
                logger.info(
                    f"League {league_id}: Data is fresh "
                    f"(synced {int(minutes_since_sync)} min ago), skipping sync"
                )
                return False

        # Check if a sync was attempted very recently (30-second debounce)
        # This prevents hammering if multiple users click at the same time
        if league_id in self._last_sync_attempt:
            time_since_attempt = now - self._last_sync_attempt[league_id]
            seconds_since_attempt = time_since_attempt.total_seconds()

            if seconds_since_attempt < 30:
                logger.info(
                    f"League {league_id}: Sync attempted {int(seconds_since_attempt)}s ago, "
                    "debouncing"
                )
                return False

        return True

    def try_acquire_sync_lock(self, league_id: str) -> bool:
        """
        Try to acquire sync lock for a league (non-blocking).

        Args:
            league_id: League identifier

        Returns:
            True if lock was acquired, False if already locked
        """
        lock = self._get_league_lock(league_id)
        acquired = lock.acquire(blocking=False)

        if acquired:
            self._last_sync_attempt[league_id] = datetime.now(timezone.utc)
            logger.info(f"League {league_id}: Sync lock acquired")
        else:
            logger.info(
                f"League {league_id}: Sync already in progress by another request"
            )

        return acquired

    def release_sync_lock(self, league_id: str):
        """
        Release sync lock for a league.

        Args:
            league_id: League identifier
        """
        lock = self._get_league_lock(league_id)
        try:
            lock.release()
            logger.info(f"League {league_id}: Sync lock released")
        except RuntimeError:
            # Lock wasn't held, this is fine (defensive programming)
            logger.warning(f"League {league_id}: Attempted to release unheld lock")


# Global singleton instance
_sync_manager_instance = None
_instance_lock = threading.Lock()


def get_sync_manager(ttl_minutes: int = 15) -> LeagueSyncManager:
    """
    Get or create the global sync manager singleton instance.
    Thread-safe lazy initialization.

    Args:
        ttl_minutes: TTL in minutes (only used on first initialization)

    Returns:
        LeagueSyncManager instance
    """
    global _sync_manager_instance

    if _sync_manager_instance is None:
        with _instance_lock:
            # Double-check pattern
            if _sync_manager_instance is None:
                _sync_manager_instance = LeagueSyncManager(ttl_minutes=ttl_minutes)
                logger.info(f"Initialized LeagueSyncManager with {ttl_minutes} min TTL")

    return _sync_manager_instance