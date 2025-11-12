"""
Henrik API storage repository.

Handles persistent caching of Henrik API responses (matches, player stats, accounts)
with automatic cleanup based on size limits.
"""

import sqlite3
import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from threading import RLock


class HenrikStorageRepository:
    """Repository for Henrik API response caching and storage."""

    def __init__(self, get_connection_func, lock: RLock):
        """
        Initialize repository with connection function and lock.

        Args:
            get_connection_func: Function that returns a database connection
            lock: Thread lock for synchronization
        """
        self._get_connection = get_connection_func
        self._lock = lock

    def get_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        Get stored match data.

        Args:
            match_id: Match identifier

        Returns:
            Match data or None if not found or expired
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("""
                    SELECT match_data, stored_at FROM henrik_matches
                    WHERE match_id = ?
                """, (match_id,)).fetchone()

                if not row:
                    return None

                # Update last_accessed
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE henrik_matches SET last_accessed = ?
                    WHERE match_id = ?
                """, (now, match_id))
                conn.commit()

                return json.loads(row['match_data'])

            except Exception as e:
                logging.error(f"Error getting stored match {match_id}: {e}")
                return None
            finally:
                conn.close()

    def store_match(self, match_id: str, match_data: Dict[str, Any]) -> bool:
        """
        Store match data.

        Args:
            match_id: Match identifier
            match_data: Match data to store

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                match_json = json.dumps(match_data)
                data_size = len(match_json)

                conn.execute("""
                    INSERT INTO henrik_matches (match_id, match_data, stored_at, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(match_id) DO UPDATE SET
                        match_data = ?,
                        last_accessed = ?,
                        data_size = ?
                """, (match_id, match_json, now, now, data_size, match_json, now, data_size))

                conn.commit()

                # Check if cleanup is needed
                self._check_and_cleanup_matches(conn, max_size_mb=50)

                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error storing match {match_id}: {e}")
                return False
            finally:
                conn.close()

    def get_player_stats(self, puuid: str, game_mode: str = None, match_count: int = 5,
                        max_age_minutes: int = 10) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Get stored player statistics.

        Args:
            puuid: Player UUID
            game_mode: Game mode filter
            match_count: Number of matches
            max_age_minutes: Maximum age in minutes

        Returns:
            Tuple of (stats_data, match_history) or None if not found or expired
        """
        with self._lock:
            conn = self._get_connection()
            try:
                stats_key = f"{puuid}_{game_mode or 'any'}_{match_count}"

                row = conn.execute("""
                    SELECT stats_data, match_history_data, stored_at FROM henrik_player_stats
                    WHERE stats_key = ?
                """, (stats_key,)).fetchone()

                if not row:
                    return None

                # Check if data is still fresh
                stored_at = datetime.fromisoformat(row['stored_at'])
                age_minutes = (datetime.now(timezone.utc) - stored_at).total_seconds() / 60

                if age_minutes > max_age_minutes:
                    return None

                # Update last_accessed
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE henrik_player_stats SET last_accessed = ?
                    WHERE stats_key = ?
                """, (now, stats_key))
                conn.commit()

                stats_data = json.loads(row['stats_data'])
                match_history = json.loads(row['match_history_data'])

                return (stats_data, match_history)

            except Exception as e:
                logging.error(f"Error getting stored player stats for {puuid}: {e}")
                return None
            finally:
                conn.close()

    def store_player_stats(self, puuid: str, game_mode: str, match_count: int,
                          stats_data: Dict[str, Any], match_history: List[Dict[str, Any]]) -> bool:
        """
        Store player statistics.

        Args:
            puuid: Player UUID
            game_mode: Game mode
            match_count: Number of matches
            stats_data: Statistics data
            match_history: Match history list

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                stats_key = f"{puuid}_{game_mode}_{match_count}"

                stats_json = json.dumps(stats_data)
                history_json = json.dumps(match_history)
                data_size = len(stats_json) + len(history_json)

                conn.execute("""
                    INSERT INTO henrik_player_stats
                    (stats_key, puuid, game_mode, match_count, stats_data, match_history_data,
                     stored_at, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stats_key) DO UPDATE SET
                        stats_data = ?,
                        match_history_data = ?,
                        stored_at = ?,
                        last_accessed = ?,
                        data_size = ?
                """, (stats_key, puuid, game_mode, match_count, stats_json, history_json,
                     now, now, data_size, stats_json, history_json, now, now, data_size))

                conn.commit()

                # Check if cleanup is needed
                self._check_and_cleanup_player_stats(conn, max_size_mb=20)

                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error storing player stats for {puuid}: {e}")
                return False
            finally:
                conn.close()

    def get_account(self, username: str = None, tag: str = None,
                   puuid: str = None) -> Optional[Dict[str, Any]]:
        """
        Get stored account data.

        Args:
            username: Valorant username
            tag: Valorant tag
            puuid: Player UUID

        Returns:
            Account data or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                if puuid:
                    account_key = puuid
                elif username and tag:
                    account_key = f"{username}_{tag}"
                else:
                    return None

                row = conn.execute("""
                    SELECT account_data, stored_at FROM henrik_accounts
                    WHERE account_key = ?
                """, (account_key,)).fetchone()

                if not row:
                    return None

                # Update last_accessed
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE henrik_accounts SET last_accessed = ?
                    WHERE account_key = ?
                """, (now, account_key))
                conn.commit()

                return json.loads(row['account_data'])

            except Exception as e:
                logging.error(f"Error getting stored account: {e}")
                return None
            finally:
                conn.close()

    def store_account(self, account_data: Dict[str, Any], username: str = None,
                     tag: str = None, puuid: str = None) -> bool:
        """
        Store account data.

        Args:
            account_data: Account data to store
            username: Valorant username
            tag: Valorant tag
            puuid: Player UUID

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                # Determine account key
                if puuid:
                    account_key = puuid
                elif username and tag:
                    account_key = f"{username}_{tag}"
                else:
                    logging.error("Must provide either puuid or username+tag")
                    return False

                account_json = json.dumps(account_data)
                data_size = len(account_json)

                conn.execute("""
                    INSERT INTO henrik_accounts
                    (account_key, username, tag, puuid, account_data, stored_at, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_key) DO UPDATE SET
                        username = ?,
                        tag = ?,
                        puuid = ?,
                        account_data = ?,
                        last_accessed = ?,
                        data_size = ?
                """, (account_key, username, tag, puuid, account_json, now, now, data_size,
                     username, tag, puuid, account_json, now, data_size))

                conn.commit()

                # Check if cleanup is needed
                self._check_and_cleanup_accounts(conn, max_size_mb=5)

                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error storing account: {e}")
                return False
            finally:
                conn.close()

    def _check_and_cleanup_matches(self, conn, max_size_mb: int = 50) -> None:
        """
        Check and cleanup match storage if size exceeds limit.

        Args:
            conn: Database connection
            max_size_mb: Maximum size in megabytes
        """
        try:
            # Get total size
            row = conn.execute("SELECT SUM(data_size) as total FROM henrik_matches").fetchone()
            total_size_mb = (row['total'] or 0) / (1024 * 1024)

            if total_size_mb > max_size_mb:
                # Delete least recently accessed matches
                to_delete = int((total_size_mb - max_size_mb * 0.8) * 1024 * 1024)
                conn.execute("""
                    DELETE FROM henrik_matches
                    WHERE match_id IN (
                        SELECT match_id FROM henrik_matches
                        ORDER BY last_accessed ASC
                        LIMIT (SELECT COUNT(*) FROM henrik_matches WHERE
                               (SELECT SUM(data_size) FROM henrik_matches) > ?)
                    )
                """, (to_delete,))
                conn.commit()
                logging.info(f"Cleaned up henrik_matches storage (was {total_size_mb:.2f}MB)")

        except Exception as e:
            logging.error(f"Error in match cleanup: {e}")

    def _check_and_cleanup_player_stats(self, conn, max_size_mb: int = 20) -> None:
        """
        Check and cleanup player stats storage if size exceeds limit.

        Args:
            conn: Database connection
            max_size_mb: Maximum size in megabytes
        """
        try:
            row = conn.execute("SELECT SUM(data_size) as total FROM henrik_player_stats").fetchone()
            total_size_mb = (row['total'] or 0) / (1024 * 1024)

            if total_size_mb > max_size_mb:
                to_delete = int((total_size_mb - max_size_mb * 0.8) * 1024 * 1024)
                conn.execute("""
                    DELETE FROM henrik_player_stats
                    WHERE stats_key IN (
                        SELECT stats_key FROM henrik_player_stats
                        ORDER BY last_accessed ASC
                        LIMIT (SELECT COUNT(*) FROM henrik_player_stats WHERE
                               (SELECT SUM(data_size) FROM henrik_player_stats) > ?)
                    )
                """, (to_delete,))
                conn.commit()
                logging.info(f"Cleaned up henrik_player_stats storage (was {total_size_mb:.2f}MB)")

        except Exception as e:
            logging.error(f"Error in player stats cleanup: {e}")

    def _check_and_cleanup_accounts(self, conn, max_size_mb: int = 5) -> None:
        """
        Check and cleanup account storage if size exceeds limit.

        Args:
            conn: Database connection
            max_size_mb: Maximum size in megabytes
        """
        try:
            row = conn.execute("SELECT SUM(data_size) as total FROM henrik_accounts").fetchone()
            total_size_mb = (row['total'] or 0) / (1024 * 1024)

            if total_size_mb > max_size_mb:
                to_delete = int((total_size_mb - max_size_mb * 0.8) * 1024 * 1024)
                conn.execute("""
                    DELETE FROM henrik_accounts
                    WHERE account_key IN (
                        SELECT account_key FROM henrik_accounts
                        ORDER BY last_accessed ASC
                        LIMIT (SELECT COUNT(*) FROM henrik_accounts WHERE
                               (SELECT SUM(data_size) FROM henrik_accounts) > ?)
                    )
                """, (to_delete,))
                conn.commit()
                logging.info(f"Cleaned up henrik_accounts storage (was {total_size_mb:.2f}MB)")

        except Exception as e:
            logging.error(f"Error in accounts cleanup: {e}")

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics for Henrik API data.

        Returns:
            Dictionary with storage statistics
        """
        with self._lock:
            conn = self._get_connection()
            try:
                matches_row = conn.execute("""
                    SELECT COUNT(*) as count, SUM(data_size) as size FROM henrik_matches
                """).fetchone()

                stats_row = conn.execute("""
                    SELECT COUNT(*) as count, SUM(data_size) as size FROM henrik_player_stats
                """).fetchone()

                accounts_row = conn.execute("""
                    SELECT COUNT(*) as count, SUM(data_size) as size FROM henrik_accounts
                """).fetchone()

                return {
                    'matches': {
                        'count': matches_row['count'],
                        'size_mb': (matches_row['size'] or 0) / (1024 * 1024)
                    },
                    'player_stats': {
                        'count': stats_row['count'],
                        'size_mb': (stats_row['size'] or 0) / (1024 * 1024)
                    },
                    'accounts': {
                        'count': accounts_row['count'],
                        'size_mb': (accounts_row['size'] or 0) / (1024 * 1024)
                    },
                    'total_size_mb': (
                        (matches_row['size'] or 0) +
                        (stats_row['size'] or 0) +
                        (accounts_row['size'] or 0)
                    ) / (1024 * 1024)
                }

            except Exception as e:
                logging.error(f"Error getting Henrik storage stats: {e}")
                return {}
            finally:
                conn.close()

    def clear_all(self) -> bool:
        """
        Clear all Henrik API storage.

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM henrik_matches")
                conn.execute("DELETE FROM henrik_player_stats")
                conn.execute("DELETE FROM henrik_accounts")
                conn.commit()

                logging.info("Cleared all Henrik API storage")
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error clearing Henrik storage: {e}")
                return False
            finally:
                conn.close()
