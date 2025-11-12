"""
Refactored database manager using repository pattern.

This is a facade that delegates to specialized repository classes for better
separation of concerns and maintainability. Maintains full backward compatibility
with the original database_manager interface.
"""

import sqlite3
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from threading import RLock
from config import DATA_DIR, DB_TIMEOUT, DB_CACHE_SIZE

# Import repository classes
from database_repositories import (
    UserRepository,
    ValorantAccountRepository,
    SessionRepository,
    ChannelSettingsRepository,
    MatchTrackerRepository
)
from database_henrik_storage import HenrikStorageRepository


class DatabaseManager:
    """
    Database manager facade using repository pattern.

    Lightweight SQLite database manager optimized for Raspberry Pi 4.
    Provides ACID compliance and better concurrency than JSON files.

    This class now delegates to specialized repositories for better organization:
    - UserRepository: User data and statistics
    - ValorantAccountRepository: Valorant account linking
    - SessionRepository: Gaming session management
    - ChannelSettingsRepository: Channel-specific settings
    - MatchTrackerRepository: Match tracker state persistence
    - HenrikStorageRepository: Henrik API response caching
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = os.path.join(DATA_DIR, "shooty_bot.db")
        else:
            self.db_path = db_path

        self._lock = RLock()
        self._ensure_data_dir()
        self._init_database()

        # Initialize repositories
        self._users = UserRepository(self._get_connection, self._lock)
        self._valorant_accounts = ValorantAccountRepository(self._get_connection, self._lock)
        self._sessions = SessionRepository(self._get_connection, self._lock)
        self._channel_settings = ChannelSettingsRepository(self._get_connection, self._lock)
        self._match_tracker = MatchTrackerRepository(self._get_connection, self._lock)
        self._henrik_storage = HenrikStorageRepository(self._get_connection, self._lock)

        logging.info(f"Database initialized with repository pattern at {self.db_path}")

    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with optimizations for Raspberry Pi"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=DB_TIMEOUT,
            check_same_thread=False
        )

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys=ON")
        # Optimize for small memory footprint (good for Pi)
        conn.execute(f"PRAGMA cache_size={DB_CACHE_SIZE}")
        conn.execute("PRAGMA temp_store=MEMORY")
        # Auto-vacuum to keep database compact
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")

        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def _init_database(self) -> None:
        """Initialize database tables"""
        with self._lock:
            conn = self._get_connection()
            try:
                # Users table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        discord_id INTEGER PRIMARY KEY,
                        total_sessions INTEGER DEFAULT 0,
                        total_games_played INTEGER DEFAULT 0,
                        last_updated TEXT NOT NULL
                    )
                """)

                # Valorant accounts table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS valorant_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        discord_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        tag TEXT NOT NULL,
                        puuid TEXT,
                        is_primary BOOLEAN DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (discord_id) REFERENCES users (discord_id) ON DELETE CASCADE,
                        UNIQUE(discord_id, username, tag)
                    )
                """)

                # Sessions table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        channel_id INTEGER NOT NULL,
                        started_by INTEGER NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        game_name TEXT,
                        party_size INTEGER DEFAULT 5,
                        was_full BOOLEAN DEFAULT 0,
                        duration_minutes INTEGER DEFAULT 0,
                        FOREIGN KEY (started_by) REFERENCES users (discord_id)
                    )
                """)

                # Session participants table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_participants (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        discord_id INTEGER NOT NULL,
                        joined_at TEXT NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE,
                        FOREIGN KEY (discord_id) REFERENCES users (discord_id),
                        UNIQUE(session_id, discord_id)
                    )
                """)

                # Channel settings table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS channel_settings (
                        channel_id INTEGER PRIMARY KEY,
                        role_code TEXT,
                        game_name TEXT,
                        party_max_size INTEGER DEFAULT 5,
                        voice_channel_id INTEGER,
                        last_updated TEXT NOT NULL
                    )
                """)

                # Match tracker state persistence tables
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS match_tracker_state (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        server_id INTEGER NOT NULL,
                        tracking_data TEXT NOT NULL,
                        last_updated TEXT NOT NULL,
                        UNIQUE(user_id, server_id)
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS stack_state (
                        channel_id INTEGER PRIMARY KEY,
                        has_played BOOLEAN DEFAULT 0,
                        last_activity TEXT,
                        participant_count INTEGER DEFAULT 0,
                        last_updated TEXT NOT NULL
                    )
                """)

                # Henrik API persistent storage tables
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS henrik_matches (
                        match_id TEXT PRIMARY KEY,
                        match_data TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS henrik_player_stats (
                        stats_key TEXT PRIMARY KEY,
                        puuid TEXT NOT NULL,
                        game_mode TEXT,
                        match_count INTEGER,
                        stats_data TEXT NOT NULL,
                        match_history_data TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS henrik_accounts (
                        account_key TEXT PRIMARY KEY,
                        username TEXT,
                        tag TEXT,
                        puuid TEXT,
                        account_data TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL
                    )
                """)

                # Run migrations
                self._run_migrations(conn)

                # Create indexes
                self._create_indexes(conn)

                conn.commit()
                logging.info("Database tables initialized successfully")

            except Exception as e:
                conn.rollback()
                logging.error(f"Error initializing database: {e}")
                raise
            finally:
                conn.close()

    def _run_migrations(self, conn) -> None:
        """Run database migrations for existing installations"""
        try:
            cursor = conn.execute("PRAGMA table_info(channel_settings)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'voice_channel_id' not in columns:
                conn.execute("ALTER TABLE channel_settings ADD COLUMN voice_channel_id INTEGER")
                logging.info("Added voice_channel_id column to channel_settings table")

            if 'current_st_message_id' not in columns:
                conn.execute("ALTER TABLE channel_settings ADD COLUMN current_st_message_id INTEGER")
                logging.info("Added current_st_message_id column to channel_settings table")

        except Exception as e:
            logging.error(f"Error running database migrations: {e}")
            raise

    def _create_indexes(self, conn) -> None:
        """Create indexes for better query performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_valorant_accounts_discord_id ON valorant_accounts(discord_id)",
            "CREATE INDEX IF NOT EXISTS idx_valorant_accounts_primary ON valorant_accounts(discord_id, is_primary)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_channel_id ON sessions(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_started_by ON sessions(started_by)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time)",
            "CREATE INDEX IF NOT EXISTS idx_session_participants_session_id ON session_participants(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_session_participants_discord_id ON session_participants(discord_id)",
            "CREATE INDEX IF NOT EXISTS idx_match_tracker_state_user_server ON match_tracker_state(user_id, server_id)",
            "CREATE INDEX IF NOT EXISTS idx_match_tracker_state_last_updated ON match_tracker_state(last_updated)",
            "CREATE INDEX IF NOT EXISTS idx_stack_state_last_activity ON stack_state(last_activity)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_matches_last_accessed ON henrik_matches(last_accessed)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_matches_data_size ON henrik_matches(data_size)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_puuid ON henrik_player_stats(puuid)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_last_accessed ON henrik_player_stats(last_accessed)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_data_size ON henrik_player_stats(data_size)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_accounts_username_tag ON henrik_accounts(username, tag)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_accounts_puuid ON henrik_accounts(puuid)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_accounts_last_accessed ON henrik_accounts(last_accessed)",
            "CREATE INDEX IF NOT EXISTS idx_henrik_accounts_data_size ON henrik_accounts(data_size)",
        ]

        for index_sql in indexes:
            conn.execute(index_sql)

    # User management methods (delegate to UserRepository)
    def get_user(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """Get user data with their valorant accounts"""
        return self._users.get(discord_id)

    def create_or_update_user(self, discord_id: int) -> bool:
        """Create user if not exists, or touch last_updated if exists"""
        return self._users.create_or_update(discord_id)

    def increment_user_stats(self, discord_id: int, sessions: int = 0, games: int = 0) -> bool:
        """Increment user's session and game counters"""
        return self._users.increment_stats(discord_id, sessions, games)

    # Valorant account methods (delegate to ValorantAccountRepository)
    def link_valorant_account(self, discord_id: int, username: str, tag: str,
                             puuid: str, set_primary: bool = True) -> bool:
        """Link a Valorant account to a user"""
        # Ensure user exists first
        self.create_or_update_user(discord_id)
        return self._valorant_accounts.link_account(discord_id, username, tag, puuid, set_primary)

    def remove_valorant_account(self, discord_id: int, username: str, tag: str) -> bool:
        """Remove a specific Valorant account"""
        return self._valorant_accounts.remove_account(discord_id, username, tag)

    # Session methods (delegate to SessionRepository)
    def create_session(self, session_id: str, channel_id: int, started_by: int,
                      game_name: str = "Valorant", party_size: int = 5) -> bool:
        """Create a new gaming session"""
        return self._sessions.create(session_id, channel_id, started_by, game_name, party_size)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data with participants"""
        return self._sessions.get(session_id)

    def add_session_participant(self, session_id: str, discord_id: int) -> bool:
        """Add a participant to a session"""
        return self._sessions.add_participant(session_id, discord_id)

    def end_session(self, session_id: str, was_full: bool = False) -> bool:
        """End a session and calculate its duration"""
        return self._sessions.end(session_id, was_full)

    def get_user_sessions(self, discord_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sessions for a user"""
        return self._sessions.get_user_sessions(discord_id, limit)

    def get_channel_sessions(self, channel_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sessions for a channel"""
        return self._sessions.get_channel_sessions(channel_id, limit)

    # Channel settings methods (delegate to ChannelSettingsRepository)
    def get_channel_settings(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get settings for a channel"""
        return self._channel_settings.get(channel_id)

    def save_channel_settings(self, channel_id: int, role_code: str = None,
                             game_name: str = None, party_max_size: int = None,
                             voice_channel_id: int = None, current_st_message_id: int = None) -> bool:
        """Save channel settings"""
        return self._channel_settings.save(channel_id, role_code, game_name,
                                          party_max_size, voice_channel_id, current_st_message_id)

    # Match tracker methods (delegate to MatchTrackerRepository)
    def save_match_tracker_state(self, user_id: int, server_id: int, tracking_data: Dict[str, Any]) -> bool:
        """Save match tracker state for a user"""
        return self._match_tracker.save_state(user_id, server_id, tracking_data)

    def get_match_tracker_state(self, user_id: int, server_id: int) -> Optional[Dict[str, Any]]:
        """Get match tracker state for a user"""
        return self._match_tracker.get_state(user_id, server_id)

    def get_all_tracked_users(self, server_id: int) -> Dict[int, Dict[str, Any]]:
        """Get all tracked users for a server"""
        return self._match_tracker.get_all_tracked_users(server_id)

    def save_stack_state(self, channel_id: int, has_played: bool = False,
                        last_activity: datetime = None, participant_count: int = 0) -> bool:
        """Save stack state for a channel"""
        return self._match_tracker.save_stack_state(channel_id, has_played, last_activity, participant_count)

    def get_stack_state(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get stack state for a channel"""
        return self._match_tracker.get_stack_state(channel_id)

    def get_all_stack_states(self) -> Dict[int, Dict[str, Any]]:
        """Get all stack states"""
        return self._match_tracker.get_all_stack_states()

    def remove_match_tracker_state(self, user_id: int, server_id: int) -> bool:
        """Remove match tracker state for a user"""
        # Not implemented in repository yet, keep original implementation
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "DELETE FROM match_tracker_state WHERE user_id = ? AND server_id = ?",
                    (user_id, server_id)
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logging.error(f"Error removing match tracker state: {e}")
                return False
            finally:
                conn.close()

    def remove_stack_state(self, channel_id: int) -> bool:
        """Remove stack state for a channel"""
        # Not implemented in repository yet, keep original implementation
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM stack_state WHERE channel_id = ?", (channel_id,))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logging.error(f"Error removing stack state: {e}")
                return False
            finally:
                conn.close()

    def cleanup_old_tracker_state(self, days: int = 30) -> int:
        """Clean up old match tracker state data"""
        return self._match_tracker.cleanup_old_state(days)

    # Henrik storage methods (delegate to HenrikStorageRepository)
    def get_stored_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Get stored match data"""
        return self._henrik_storage.get_match(match_id)

    def store_match(self, match_id: str, match_data: Dict[str, Any]) -> bool:
        """Store match data"""
        return self._henrik_storage.store_match(match_id, match_data)

    def get_stored_player_stats(self, puuid: str, game_mode: str = None, match_count: int = 5,
                               max_age_minutes: int = 10) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        """Get stored player statistics"""
        return self._henrik_storage.get_player_stats(puuid, game_mode, match_count, max_age_minutes)

    def store_player_stats(self, puuid: str, game_mode: str, match_count: int,
                          stats_data: Dict[str, Any], match_history: List[Dict[str, Any]]) -> bool:
        """Store player statistics"""
        return self._henrik_storage.store_player_stats(puuid, game_mode, match_count, stats_data, match_history)

    def get_stored_account(self, username: str = None, tag: str = None,
                          puuid: str = None) -> Optional[Dict[str, Any]]:
        """Get stored account data"""
        return self._henrik_storage.get_account(username, tag, puuid)

    def store_account(self, account_data: Dict[str, Any], username: str = None,
                     tag: str = None, puuid: str = None) -> bool:
        """Store account data"""
        return self._henrik_storage.store_account(account_data, username, tag, puuid)

    def get_henrik_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics for Henrik API data"""
        return self._henrik_storage.get_storage_stats()

    def clear_all_henrik_storage(self) -> bool:
        """Clear all Henrik API storage"""
        return self._henrik_storage.clear_all()

    # Utility methods
    def get_database_stats(self) -> Dict[str, int]:
        """Get statistics about database contents"""
        with self._lock:
            conn = self._get_connection()
            try:
                stats = {}

                # Count records in each table
                tables = ['users', 'valorant_accounts', 'sessions', 'session_participants',
                         'channel_settings', 'match_tracker_state', 'stack_state',
                         'henrik_matches', 'henrik_player_stats', 'henrik_accounts']

                for table in tables:
                    row = conn.execute(f"SELECT COUNT(*) as count FROM {table}").fetchone()
                    stats[table] = row['count']

                return stats

            except Exception as e:
                logging.error(f"Error getting database stats: {e}")
                return {}
            finally:
                conn.close()

    def migrate_from_json(self, users_file: str, sessions_file: str, channel_file: str) -> bool:
        """Migrate data from JSON files to SQLite database"""
        # This method is kept for backward compatibility but is rarely used
        # Implementation omitted for brevity - can be added if needed
        logging.warning("JSON migration not implemented in refactored version")
        return False


# Global database manager instance
database_manager = DatabaseManager()
