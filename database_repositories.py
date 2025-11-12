"""
Database repositories for ShootyBot.

This module contains specialized repository classes that handle specific data domains,
following the Repository pattern for better separation of concerns and testability.

Extracted from database.py to reduce complexity and improve maintainability.
"""

import sqlite3
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from threading import RLock


class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, get_connection_func, lock: RLock):
        """
        Initialize repository with connection function and lock.

        Args:
            get_connection_func: Function that returns a database connection
            lock: Thread lock for synchronization
        """
        self._get_connection = get_connection_func
        self._lock = lock

    def _execute_query(self, query: str, params: tuple = (), fetch_one: bool = False,
                      fetch_all: bool = False, commit: bool = False) -> Any:
        """
        Execute a database query with proper error handling.

        Args:
            query: SQL query string
            params: Query parameters
            fetch_one: Whether to fetch one result
            fetch_all: Whether to fetch all results
            commit: Whether to commit the transaction

        Returns:
            Query results or None on error
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(query, params)

                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()

                if commit:
                    conn.commit()

                return cursor

            except Exception as e:
                if commit:
                    conn.rollback()
                logging.error(f"Database query error: {e}")
                logging.error(f"Query: {query}")
                raise
            finally:
                conn.close()


class UserRepository(BaseRepository):
    """Repository for user-related database operations."""

    def get(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user data with their Valorant accounts and session history.

        Args:
            discord_id: Discord user ID

        Returns:
            Dictionary containing user data or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                # Get user base data
                user_row = conn.execute(
                    "SELECT * FROM users WHERE discord_id = ?",
                    (discord_id,)
                ).fetchone()

                if not user_row:
                    return None

                # Get Valorant accounts
                accounts_rows = conn.execute("""
                    SELECT username, tag, puuid, is_primary
                    FROM valorant_accounts
                    WHERE discord_id = ?
                    ORDER BY is_primary DESC, created_at ASC
                """, (discord_id,)).fetchall()

                # Get session history
                session_history_rows = conn.execute("""
                    SELECT DISTINCT s.session_id
                    FROM sessions s
                    JOIN session_participants sp ON s.session_id = sp.session_id
                    WHERE sp.discord_id = ?
                    ORDER BY s.start_time DESC
                    LIMIT 50
                """, (discord_id,)).fetchall()

                return {
                    'discord_id': user_row['discord_id'],
                    'total_sessions': user_row['total_sessions'],
                    'total_games_played': user_row['total_games_played'],
                    'last_updated': user_row['last_updated'],
                    'valorant_accounts': [dict(row) for row in accounts_rows],
                    'session_history': [row['session_id'] for row in session_history_rows]
                }

            except Exception as e:
                logging.error(f"Error getting user {discord_id}: {e}")
                return None
            finally:
                conn.close()

    def create_or_update(self, discord_id: int) -> bool:
        """
        Create user if not exists, or update last_updated timestamp if exists.

        Args:
            discord_id: Discord user ID

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                conn.execute("""
                    INSERT INTO users (discord_id, last_updated)
                    VALUES (?, ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        last_updated = ?
                """, (discord_id, now, now))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error creating/updating user {discord_id}: {e}")
                return False
            finally:
                conn.close()

    def increment_stats(self, discord_id: int, sessions: int = 0, games: int = 0) -> bool:
        """
        Increment user's session and game counters.

        Args:
            discord_id: Discord user ID
            sessions: Number of sessions to add
            games: Number of games to add

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                conn.execute("""
                    UPDATE users
                    SET total_sessions = total_sessions + ?,
                        total_games_played = total_games_played + ?,
                        last_updated = ?
                    WHERE discord_id = ?
                """, (sessions, games, now, discord_id))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error incrementing stats for user {discord_id}: {e}")
                return False
            finally:
                conn.close()


class ValorantAccountRepository(BaseRepository):
    """Repository for Valorant account linking operations."""

    def link_account(self, discord_id: int, username: str, tag: str,
                    puuid: str, set_primary: bool = True) -> bool:
        """
        Link a Valorant account to a Discord user.

        Args:
            discord_id: Discord user ID
            username: Valorant username
            tag: Valorant tag
            puuid: Player UUID
            set_primary: Whether to set this as the primary account

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                # If setting as primary, unmark other primary accounts
                if set_primary:
                    conn.execute("""
                        UPDATE valorant_accounts
                        SET is_primary = 0
                        WHERE discord_id = ?
                    """, (discord_id,))

                # Insert or update account
                conn.execute("""
                    INSERT INTO valorant_accounts (discord_id, username, tag, puuid, is_primary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(discord_id, username, tag) DO UPDATE SET
                        puuid = ?,
                        is_primary = ?
                """, (discord_id, username, tag, puuid, set_primary, now, puuid, set_primary))

                # Update user last_updated
                conn.execute("""
                    UPDATE users SET last_updated = ? WHERE discord_id = ?
                """, (now, discord_id))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error linking Valorant account for {discord_id}: {e}")
                return False
            finally:
                conn.close()

    def remove_account(self, discord_id: int, username: str, tag: str) -> bool:
        """
        Remove a specific Valorant account.

        Args:
            discord_id: Discord user ID
            username: Valorant username
            tag: Valorant tag

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                # Check if it was primary
                was_primary_row = conn.execute("""
                    SELECT is_primary FROM valorant_accounts
                    WHERE discord_id = ? AND username = ? AND tag = ?
                """, (discord_id, username, tag)).fetchone()

                if not was_primary_row:
                    return False

                was_primary = was_primary_row['is_primary']

                # Remove the account
                conn.execute("""
                    DELETE FROM valorant_accounts
                    WHERE discord_id = ? AND username = ? AND tag = ?
                """, (discord_id, username, tag))

                # If it was primary, set first remaining as primary
                if was_primary:
                    conn.execute("""
                        UPDATE valorant_accounts
                        SET is_primary = 1
                        WHERE discord_id = ? AND id = (
                            SELECT MIN(id) FROM valorant_accounts WHERE discord_id = ?
                        )
                    """, (discord_id, discord_id))

                # Update user last_updated
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE users SET last_updated = ? WHERE discord_id = ?
                """, (now, discord_id))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error removing Valorant account for {discord_id}: {e}")
                return False
            finally:
                conn.close()


class SessionRepository(BaseRepository):
    """Repository for gaming session management."""

    def create(self, session_id: str, channel_id: int, started_by: int,
              game_name: str = "Valorant", party_size: int = 5) -> bool:
        """
        Create a new gaming session.

        Args:
            session_id: Unique session identifier
            channel_id: Discord channel ID
            started_by: Discord ID of user who started session
            game_name: Name of the game
            party_size: Maximum party size

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                conn.execute("""
                    INSERT INTO sessions (session_id, channel_id, started_by, start_time, game_name, party_size)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (session_id, channel_id, started_by, now, game_name, party_size))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error creating session {session_id}: {e}")
                return False
            finally:
                conn.close()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session data with participants.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary containing session data or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                session_row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if not session_row:
                    return None

                # Get participants
                participants = conn.execute("""
                    SELECT discord_id, joined_at FROM session_participants
                    WHERE session_id = ?
                    ORDER BY joined_at ASC
                """, (session_id,)).fetchall()

                return {
                    'session_id': session_row['session_id'],
                    'channel_id': session_row['channel_id'],
                    'started_by': session_row['started_by'],
                    'start_time': session_row['start_time'],
                    'end_time': session_row['end_time'],
                    'game_name': session_row['game_name'],
                    'party_size': session_row['party_size'],
                    'was_full': bool(session_row['was_full']),
                    'duration_minutes': session_row['duration_minutes'],
                    'participants': [{'discord_id': row['discord_id'], 'joined_at': row['joined_at']}
                                   for row in participants]
                }

            except Exception as e:
                logging.error(f"Error getting session {session_id}: {e}")
                return None
            finally:
                conn.close()

    def add_participant(self, session_id: str, discord_id: int) -> bool:
        """
        Add a participant to a session.

        Args:
            session_id: Session identifier
            discord_id: Discord user ID

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                conn.execute("""
                    INSERT OR IGNORE INTO session_participants (session_id, discord_id, joined_at)
                    VALUES (?, ?, ?)
                """, (session_id, discord_id, now))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error adding participant to session {session_id}: {e}")
                return False
            finally:
                conn.close()

    def end(self, session_id: str, was_full: bool = False) -> bool:
        """
        End a session and calculate its duration.

        Args:
            session_id: Session identifier
            was_full: Whether the party was full

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                # Get start time
                session_row = conn.execute(
                    "SELECT start_time FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if not session_row:
                    return False

                # Calculate duration
                start_time = datetime.fromisoformat(session_row['start_time'])
                end_time = datetime.now(timezone.utc)
                duration_minutes = int((end_time - start_time).total_seconds() / 60)

                # Update session
                conn.execute("""
                    UPDATE sessions
                    SET end_time = ?, was_full = ?, duration_minutes = ?
                    WHERE session_id = ?
                """, (now, was_full, duration_minutes, session_id))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error ending session {session_id}: {e}")
                return False
            finally:
                conn.close()

    def get_user_sessions(self, discord_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent sessions for a user.

        Args:
            discord_id: Discord user ID
            limit: Maximum number of sessions to return

        Returns:
            List of session dictionaries
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT DISTINCT s.* FROM sessions s
                    JOIN session_participants sp ON s.session_id = sp.session_id
                    WHERE sp.discord_id = ?
                    ORDER BY s.start_time DESC
                    LIMIT ?
                """, (discord_id, limit)).fetchall()

                return [dict(row) for row in rows]

            except Exception as e:
                logging.error(f"Error getting sessions for user {discord_id}: {e}")
                return []
            finally:
                conn.close()

    def get_channel_sessions(self, channel_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent sessions for a channel.

        Args:
            channel_id: Discord channel ID
            limit: Maximum number of sessions to return

        Returns:
            List of session dictionaries
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT * FROM sessions
                    WHERE channel_id = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (channel_id, limit)).fetchall()

                return [dict(row) for row in rows]

            except Exception as e:
                logging.error(f"Error getting sessions for channel {channel_id}: {e}")
                return []
            finally:
                conn.close()


class ChannelSettingsRepository(BaseRepository):
    """Repository for channel-specific settings."""

    def get(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """
        Get settings for a channel.

        Args:
            channel_id: Discord channel ID

        Returns:
            Dictionary containing settings or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM channel_settings WHERE channel_id = ?",
                    (channel_id,)
                ).fetchone()

                return dict(row) if row else None

            except Exception as e:
                logging.error(f"Error getting settings for channel {channel_id}: {e}")
                return None
            finally:
                conn.close()

    def save(self, channel_id: int, role_code: str = None, game_name: str = None,
            party_max_size: int = None, voice_channel_id: int = None,
            current_st_message_id: int = None) -> bool:
        """
        Save channel settings.

        Args:
            channel_id: Discord channel ID
            role_code: Role mention code
            game_name: Game name
            party_max_size: Maximum party size
            voice_channel_id: Associated voice channel ID
            current_st_message_id: Current session tracker message ID

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                # Build update query dynamically
                updates = []
                params = []

                if role_code is not None:
                    updates.append("role_code = ?")
                    params.append(role_code)
                if game_name is not None:
                    updates.append("game_name = ?")
                    params.append(game_name)
                if party_max_size is not None:
                    updates.append("party_max_size = ?")
                    params.append(party_max_size)
                if voice_channel_id is not None:
                    updates.append("voice_channel_id = ?")
                    params.append(voice_channel_id)
                if current_st_message_id is not None:
                    updates.append("current_st_message_id = ?")
                    params.append(current_st_message_id)

                updates.append("last_updated = ?")
                params.append(now)
                params.append(channel_id)

                query = f"""
                    INSERT INTO channel_settings (channel_id, last_updated)
                    VALUES (?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET {', '.join(updates)}
                """

                conn.execute(query, [channel_id, now] + params)
                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error saving settings for channel {channel_id}: {e}")
                return False
            finally:
                conn.close()


class MatchTrackerRepository(BaseRepository):
    """Repository for match tracker state persistence."""

    def save_state(self, user_id: int, server_id: int, tracking_data: Dict[str, Any]) -> bool:
        """
        Save match tracker state for a user.

        Args:
            user_id: Discord user ID
            server_id: Discord server ID
            tracking_data: Tracking state data

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                tracking_json = json.dumps(tracking_data)

                conn.execute("""
                    INSERT INTO match_tracker_state (user_id, server_id, tracking_data, last_updated)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, server_id) DO UPDATE SET
                        tracking_data = ?,
                        last_updated = ?
                """, (user_id, server_id, tracking_json, now, tracking_json, now))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error saving match tracker state for user {user_id}: {e}")
                return False
            finally:
                conn.close()

    def get_state(self, user_id: int, server_id: int) -> Optional[Dict[str, Any]]:
        """
        Get match tracker state for a user.

        Args:
            user_id: Discord user ID
            server_id: Discord server ID

        Returns:
            Tracking state data or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("""
                    SELECT tracking_data FROM match_tracker_state
                    WHERE user_id = ? AND server_id = ?
                """, (user_id, server_id)).fetchone()

                if row:
                    return json.loads(row['tracking_data'])
                return None

            except Exception as e:
                logging.error(f"Error getting match tracker state for user {user_id}: {e}")
                return None
            finally:
                conn.close()

    def get_all_tracked_users(self, server_id: int) -> Dict[int, Dict[str, Any]]:
        """
        Get all tracked users for a server.

        Args:
            server_id: Discord server ID

        Returns:
            Dictionary mapping user IDs to tracking data
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT user_id, tracking_data FROM match_tracker_state
                    WHERE server_id = ?
                """, (server_id,)).fetchall()

                return {row['user_id']: json.loads(row['tracking_data']) for row in rows}

            except Exception as e:
                logging.error(f"Error getting tracked users for server {server_id}: {e}")
                return {}
            finally:
                conn.close()

    def save_stack_state(self, channel_id: int, has_played: bool = False,
                        last_activity: datetime = None, participant_count: int = 0) -> bool:
        """
        Save stack state for a channel.

        Args:
            channel_id: Discord channel ID
            has_played: Whether the stack has played games
            last_activity: Last activity timestamp
            participant_count: Number of participants

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                last_activity_str = last_activity.isoformat() if last_activity else None

                conn.execute("""
                    INSERT INTO stack_state (channel_id, has_played, last_activity, participant_count, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        has_played = ?,
                        last_activity = ?,
                        participant_count = ?,
                        last_updated = ?
                """, (channel_id, has_played, last_activity_str, participant_count, now,
                     has_played, last_activity_str, participant_count, now))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logging.error(f"Error saving stack state for channel {channel_id}: {e}")
                return False
            finally:
                conn.close()

    def get_stack_state(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """
        Get stack state for a channel.

        Args:
            channel_id: Discord channel ID

        Returns:
            Stack state data or None if not found
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("""
                    SELECT * FROM stack_state WHERE channel_id = ?
                """, (channel_id,)).fetchone()

                if not row:
                    return None

                result = dict(row)
                # Parse last_activity back to datetime if present
                if result['last_activity']:
                    result['last_activity'] = datetime.fromisoformat(result['last_activity'])

                return result

            except Exception as e:
                logging.error(f"Error getting stack state for channel {channel_id}: {e}")
                return None
            finally:
                conn.close()

    def get_all_stack_states(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all stack states.

        Returns:
            Dictionary mapping channel IDs to stack state data
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("SELECT * FROM stack_state").fetchall()

                result = {}
                for row in rows:
                    channel_id = row['channel_id']
                    state = dict(row)
                    # Parse last_activity back to datetime if present
                    if state['last_activity']:
                        state['last_activity'] = datetime.fromisoformat(state['last_activity'])
                    result[channel_id] = state

                return result

            except Exception as e:
                logging.error(f"Error getting all stack states: {e}")
                return {}
            finally:
                conn.close()

    def cleanup_old_state(self, days: int = 30) -> int:
        """
        Clean up old tracker state data.

        Args:
            days: Number of days to keep

        Returns:
            Number of records deleted
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

                cursor = conn.execute("""
                    DELETE FROM match_tracker_state
                    WHERE last_updated < ?
                """, (cutoff_date,))

                deleted_count = cursor.rowcount
                conn.commit()

                logging.info(f"Cleaned up {deleted_count} old match tracker state records")
                return deleted_count

            except Exception as e:
                conn.rollback()
                logging.error(f"Error cleaning up old tracker state: {e}")
                return 0
            finally:
                conn.close()
