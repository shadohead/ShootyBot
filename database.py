import sqlite3
import logging
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from threading import RLock
from config import DATA_DIR

class DatabaseManager:
    """
    Lightweight SQLite database manager optimized for Raspberry Pi 4.
    Provides ACID compliance and better concurrency than JSON files.
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = os.path.join(DATA_DIR, "shooty_bot.db")
        else:
            self.db_path = db_path
        
        self._lock = RLock()
        self._ensure_data_dir()
        self._init_database()
        
        logging.info(f"Database initialized at {self.db_path}")
    
    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with optimizations for Raspberry Pi"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # 30 second timeout for Pi's slower I/O
            check_same_thread=False
        )
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys=ON")
        # Optimize for small memory footprint (good for Pi)
        conn.execute("PRAGMA cache_size=-32000")  # 32MB cache
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
                
                # Session participants table (many-to-many)
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
                        tracking_data TEXT NOT NULL,  -- JSON: recent matches, last activity, etc.
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
                        match_data TEXT NOT NULL,  -- JSON string of match data
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL  -- Size of match_data in bytes
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS henrik_player_stats (
                        stats_key TEXT PRIMARY KEY,  -- Format: puuid_gamemode_matchcount (e.g., "abc123_competitive_10")
                        puuid TEXT NOT NULL,
                        game_mode TEXT,
                        match_count INTEGER,
                        stats_data TEXT NOT NULL,  -- JSON string of calculated stats
                        match_history_data TEXT NOT NULL,  -- JSON string of match list
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL  -- Size of stats_data + match_history_data in bytes
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS henrik_accounts (
                        account_key TEXT PRIMARY KEY,  -- Format: username_tag or puuid
                        username TEXT,
                        tag TEXT,
                        puuid TEXT,
                        account_data TEXT NOT NULL,  -- JSON string of account info
                        stored_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        data_size INTEGER NOT NULL  -- Size of account_data in bytes
                    )
                """)
                
                # Database migrations for existing installations
                self._run_migrations(conn)
                
                # Create indexes for better query performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_valorant_accounts_discord_id ON valorant_accounts(discord_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_valorant_accounts_primary ON valorant_accounts(discord_id, is_primary)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_channel_id ON sessions(channel_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_started_by ON sessions(started_by)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session_participants_session_id ON session_participants(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session_participants_discord_id ON session_participants(discord_id)")
                
                # Match tracker state indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_match_tracker_state_user_server ON match_tracker_state(user_id, server_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_match_tracker_state_last_updated ON match_tracker_state(last_updated)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_stack_state_last_activity ON stack_state(last_activity)")
                
                # Henrik storage indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_matches_last_accessed ON henrik_matches(last_accessed)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_matches_data_size ON henrik_matches(data_size)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_puuid ON henrik_player_stats(puuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_last_accessed ON henrik_player_stats(last_accessed)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_player_stats_data_size ON henrik_player_stats(data_size)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_accounts_username_tag ON henrik_accounts(username, tag)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_accounts_puuid ON henrik_accounts(puuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_accounts_last_accessed ON henrik_accounts(last_accessed)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_henrik_accounts_data_size ON henrik_accounts(data_size)")
                
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
            # Migration 1: Add voice_channel_id to channel_settings if missing
            cursor = conn.execute("PRAGMA table_info(channel_settings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'voice_channel_id' not in columns:
                conn.execute("ALTER TABLE channel_settings ADD COLUMN voice_channel_id INTEGER")
                logging.info("Added voice_channel_id column to channel_settings table")
        
        except Exception as e:
            logging.error(f"Error running database migrations: {e}")
            raise
    
    # User management methods
    def get_user(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """Get user data with their valorant accounts"""
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
                
                # Get valorant accounts
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
    
    def create_or_update_user(self, discord_id: int) -> bool:
        """Create user if not exists, or touch last_updated if exists"""
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
    
    def link_valorant_account(self, discord_id: int, username: str, tag: str, 
                             puuid: str, set_primary: bool = True) -> bool:
        """Link a Valorant account to a user"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Ensure user exists (inline to avoid nested connection)
                conn.execute("""
                    INSERT INTO users (discord_id, last_updated)
                    VALUES (?, ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        last_updated = ?
                """, (discord_id, now, now))
                
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
                
                conn.commit()
                return True
            
            except Exception as e:
                conn.rollback()
                logging.error(f"Error linking Valorant account for {discord_id}: {e}")
                return False
            finally:
                conn.close()
    
    def remove_valorant_account(self, discord_id: int, username: str, tag: str) -> bool:
        """Remove a specific Valorant account"""
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
    
    def increment_user_stats(self, discord_id: int, sessions: int = 0, games: int = 0) -> bool:
        """Increment user statistics"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Ensure user exists
                self.create_or_update_user(discord_id)
                
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
                logging.error(f"Error incrementing stats for {discord_id}: {e}")
                return False
            finally:
                conn.close()
    
    # Session management methods
    def create_session(self, session_id: str, channel_id: int, started_by: int, 
                      game_name: str = None, party_size: int = 5) -> bool:
        """Create a new session"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Ensure user exists
                self.create_or_update_user(started_by)
                
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
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data with participants"""
        with self._lock:
            conn = self._get_connection()
            try:
                # Get session data
                session_row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                
                if not session_row:
                    return None
                
                # Get participants
                participants_rows = conn.execute("""
                    SELECT discord_id, joined_at
                    FROM session_participants 
                    WHERE session_id = ?
                    ORDER BY joined_at ASC
                """, (session_id,)).fetchall()
                
                session_data = dict(session_row)
                session_data['participants'] = [row['discord_id'] for row in participants_rows]
                
                return session_data
            
            except Exception as e:
                logging.error(f"Error getting session {session_id}: {e}")
                return None
            finally:
                conn.close()
    
    def add_session_participant(self, session_id: str, discord_id: int) -> bool:
        """Add a participant to a session"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Ensure user exists
                self.create_or_update_user(discord_id)
                
                conn.execute("""
                    INSERT OR IGNORE INTO session_participants (session_id, discord_id, joined_at)
                    VALUES (?, ?, ?)
                """, (session_id, discord_id, now))
                
                conn.commit()
                return True
            
            except Exception as e:
                conn.rollback()
                logging.error(f"Error adding participant {discord_id} to session {session_id}: {e}")
                return False
            finally:
                conn.close()
    
    def end_session(self, session_id: str, was_full: bool = False) -> bool:
        """End a session and calculate duration"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Get start time to calculate duration
                session_row = conn.execute(
                    "SELECT start_time FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                
                if not session_row:
                    return False
                
                start_time = datetime.fromisoformat(session_row['start_time'])
                end_time = datetime.fromisoformat(now)
                duration_minutes = int((end_time - start_time).total_seconds() / 60)
                
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
        """Get recent sessions for a user"""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT DISTINCT s.*
                    FROM sessions s
                    JOIN session_participants sp ON s.session_id = sp.session_id
                    WHERE sp.discord_id = ?
                    ORDER BY s.start_time DESC
                    LIMIT ?
                """, (discord_id, limit)).fetchall()
                
                return [dict(row) for row in rows]
            
            except Exception as e:
                logging.error(f"Error getting user sessions for {discord_id}: {e}")
                return []
            finally:
                conn.close()
    
    def get_channel_sessions(self, channel_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sessions for a channel"""
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
                logging.error(f"Error getting channel sessions for {channel_id}: {e}")
                return []
            finally:
                conn.close()
    
    # Channel settings methods
    def get_channel_settings(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get channel settings"""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM channel_settings WHERE channel_id = ?",
                    (channel_id,)
                ).fetchone()
                
                return dict(row) if row else None
            
            except Exception as e:
                logging.error(f"Error getting channel settings for {channel_id}: {e}")
                return None
            finally:
                conn.close()
    
    def save_channel_settings(self, channel_id: int, role_code: str = None, 
                             game_name: str = None, party_max_size: int = 5, voice_channel_id: int = None) -> bool:
        """Save channel settings"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                conn.execute("""
                    INSERT INTO channel_settings (channel_id, role_code, game_name, party_max_size, voice_channel_id, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        role_code = COALESCE(?, role_code),
                        game_name = COALESCE(?, game_name),
                        party_max_size = COALESCE(?, party_max_size),
                        voice_channel_id = COALESCE(?, voice_channel_id),
                        last_updated = ?
                """, (channel_id, role_code, game_name, party_max_size, voice_channel_id, now,
                      role_code, game_name, party_max_size, voice_channel_id, now))
                
                conn.commit()
                return True
            
            except Exception as e:
                conn.rollback()
                logging.error(f"Error saving channel settings for {channel_id}: {e}")
                return False
            finally:
                conn.close()
    
    # Migration and utility methods
    def migrate_from_json(self, users_file: str, sessions_file: str, channel_file: str) -> bool:
        """Migrate data from existing JSON files"""
        logging.info("Starting migration from JSON files to SQLite...")
        
        try:
            # Migrate users
            if os.path.exists(users_file):
                with open(users_file, 'r') as f:
                    users_data = json.load(f)
                
                for discord_id, user_data in users_data.items():
                    discord_id = int(discord_id)
                    
                    # Create/update user
                    self.create_or_update_user(discord_id)
                    
                    # Update statistics
                    total_sessions = user_data.get('total_sessions', 0)
                    total_games = user_data.get('total_games_played', 0)
                    if total_sessions > 0 or total_games > 0:
                        self.increment_user_stats(discord_id, total_sessions, total_games)
                    
                    # Migrate Valorant accounts
                    valorant_accounts = user_data.get('valorant_accounts', [])
                    if not valorant_accounts:
                        # Handle old format
                        old_username = user_data.get('valorant_username')
                        old_tag = user_data.get('valorant_tag')
                        old_puuid = user_data.get('valorant_puuid')
                        
                        if old_username and old_tag:
                            self.link_valorant_account(
                                discord_id, old_username, old_tag, 
                                old_puuid or f"legacy_{old_username}_{old_tag}", True
                            )
                    else:
                        for account in valorant_accounts:
                            self.link_valorant_account(
                                discord_id, account['username'], account['tag'],
                                account.get('puuid', ''), account.get('primary', False)
                            )
                
                logging.info(f"Migrated {len(users_data)} users")
            
            # Migrate sessions
            if os.path.exists(sessions_file):
                with open(sessions_file, 'r') as f:
                    sessions_data = json.load(f)
                
                for session_id, session_data in sessions_data.items():
                    # Create session
                    self.create_session(
                        session_id,
                        session_data['channel_id'],
                        session_data['started_by'],
                        session_data.get('game_name'),
                        session_data.get('party_size', 5)
                    )
                    
                    # Add participants
                    for participant_id in session_data.get('participants', []):
                        self.add_session_participant(session_id, participant_id)
                    
                    # End session if applicable
                    if session_data.get('end_time'):
                        self.end_session(session_id, session_data.get('was_full', False))
                
                logging.info(f"Migrated {len(sessions_data)} sessions")
            
            # Migrate channel settings
            if os.path.exists(channel_file):
                with open(channel_file, 'r') as f:
                    channel_data = json.load(f)
                
                for channel_id, settings in channel_data.items():
                    self.save_channel_settings(
                        int(channel_id),
                        settings.get('role_code'),
                        settings.get('game_name'),
                        settings.get('party_max_size', 5)
                    )
                
                logging.info(f"Migrated {len(channel_data)} channel settings")
            
            logging.info("Migration completed successfully!")
            return True
        
        except Exception as e:
            logging.error(f"Error during migration: {e}")
            return False
    
    def vacuum_database(self) -> None:
        """Optimize database for better performance on Raspberry Pi"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("PRAGMA incremental_vacuum")
                conn.execute("VACUUM")
                logging.info("Database optimized")
            
            except Exception as e:
                logging.error(f"Error optimizing database: {e}")
            finally:
                conn.close()
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        with self._lock:
            conn = self._get_connection()
            try:
                stats = {}
                
                tables = ['users', 'valorant_accounts', 'sessions', 'session_participants', 'channel_settings', 
                         'match_tracker_state', 'stack_state', 'henrik_matches', 'henrik_player_stats', 'henrik_accounts']
                for table in tables:
                    row = conn.execute(f"SELECT COUNT(*) as count FROM {table}").fetchone()
                    stats[table] = row['count']
                
                # Database size
                size_row = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()").fetchone()
                stats['database_size_bytes'] = size_row['size']
                
                return stats
            
            except Exception as e:
                logging.error(f"Error getting database stats: {e}")
                return {}
            finally:
                conn.close()
    
    # Henrik API persistent storage methods
    def get_stored_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Get stored match data if it exists"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                # Update last_accessed when retrieving
                row = conn.execute("""
                    SELECT match_data FROM henrik_matches WHERE match_id = ?
                """, (match_id,)).fetchone()
                
                if row:
                    # Update last_accessed
                    conn.execute("""
                        UPDATE henrik_matches SET last_accessed = ? WHERE match_id = ?
                    """, (now, match_id))
                    conn.commit()
                    
                    return json.loads(row['match_data'])
                return None
            
            except Exception as e:
                logging.error(f"Error getting stored match {match_id}: {e}")
                return None
            finally:
                conn.close()
    
    def store_match(self, match_id: str, match_data: Dict[str, Any]) -> bool:
        """Store match data permanently"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                match_json = json.dumps(match_data)
                data_size = len(match_json.encode('utf-8'))
                
                conn.execute("""
                    INSERT OR REPLACE INTO henrik_matches (match_id, match_data, stored_at, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?)
                """, (match_id, match_json, now, now, data_size))
                
                conn.commit()
                
                # Check if we need size-based cleanup
                self._check_and_cleanup_matches(conn)
                
                return True
            
            except Exception as e:
                logging.error(f"Error storing match {match_id}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def get_stored_player_stats(self, puuid: str, game_mode: str = None, match_count: int = 5, max_age_minutes: int = 10) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        """Get stored player stats and match history if they exist"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                stats_key = f"{puuid}_{game_mode or 'all'}_{match_count}"
                
                row = conn.execute("""
                    SELECT stats_data, match_history_data, stored_at FROM henrik_player_stats 
                    WHERE stats_key = ?
                """, (stats_key,)).fetchone()
                
                if row:
                    # Check if data is still fresh
                    stored_at = datetime.fromisoformat(row['stored_at'])
                    age_minutes = (datetime.now(timezone.utc) - stored_at).total_seconds() / 60
                    
                    if age_minutes > max_age_minutes:
                        logging.debug(f"Cached player stats for {puuid} are {age_minutes:.1f} minutes old, exceeding {max_age_minutes} minute limit")
                        return None  # Data is too old, force refresh
                    
                    # Update last_accessed
                    conn.execute("""
                        UPDATE henrik_player_stats SET last_accessed = ? WHERE stats_key = ?
                    """, (now, stats_key))
                    conn.commit()
                    
                    stats_data = json.loads(row['stats_data'])
                    match_history_data = json.loads(row['match_history_data'])
                    return stats_data, match_history_data
                return None
            
            except Exception as e:
                logging.error(f"Error getting stored player stats {puuid}: {e}")
                return None
            finally:
                conn.close()
    
    def store_player_stats(self, puuid: str, game_mode: str, match_count: int, stats_data: Dict[str, Any], 
                          match_history_data: List[Dict[str, Any]]) -> bool:
        """Store player stats and match history permanently"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                stats_key = f"{puuid}_{game_mode or 'all'}_{match_count}"
                
                stats_json = json.dumps(stats_data)
                history_json = json.dumps(match_history_data)
                data_size = len(stats_json.encode('utf-8')) + len(history_json.encode('utf-8'))
                
                conn.execute("""
                    INSERT OR REPLACE INTO henrik_player_stats 
                    (stats_key, puuid, game_mode, match_count, stats_data, match_history_data, stored_at, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (stats_key, puuid, game_mode, match_count, stats_json, history_json, now, now, data_size))
                
                conn.commit()
                
                # Check if we need size-based cleanup
                self._check_and_cleanup_player_stats(conn)
                
                return True
            
            except Exception as e:
                logging.error(f"Error storing player stats {puuid}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def get_stored_account(self, username: str = None, tag: str = None, puuid: str = None) -> Optional[Dict[str, Any]]:
        """Get stored account data if it exists"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                
                if puuid:
                    account_key = puuid
                    row = conn.execute("""
                        SELECT account_data FROM henrik_accounts WHERE account_key = ?
                    """, (account_key,)).fetchone()
                elif username and tag:
                    account_key = f"{username}_{tag}"
                    row = conn.execute("""
                        SELECT account_data FROM henrik_accounts WHERE account_key = ?
                    """, (account_key,)).fetchone()
                else:
                    return None
                
                if row:
                    # Update last_accessed
                    conn.execute("""
                        UPDATE henrik_accounts SET last_accessed = ? WHERE account_key = ?
                    """, (now, account_key))
                    conn.commit()
                    
                    return json.loads(row['account_data'])
                return None
            
            except Exception as e:
                logging.error(f"Error getting stored account: {e}")
                return None
            finally:
                conn.close()
    
    def store_account(self, account_data: Dict[str, Any], username: str = None, tag: str = None, puuid: str = None) -> bool:
        """Store account data permanently"""
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()
                account_json = json.dumps(account_data)
                data_size = len(account_json.encode('utf-8'))
                
                # Create storage entries for both username_tag and puuid if available
                account_puuid = account_data.get('puuid') or puuid
                account_username = account_data.get('name') or username
                account_tag = account_data.get('tag') or tag
                
                # Store by username_tag
                if account_username and account_tag:
                    account_key = f"{account_username}_{account_tag}"
                    conn.execute("""
                        INSERT OR REPLACE INTO henrik_accounts 
                        (account_key, username, tag, puuid, account_data, stored_at, last_accessed, data_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (account_key, account_username, account_tag, account_puuid, account_json, now, now, data_size))
                
                # Store by puuid
                if account_puuid and account_puuid != f"{account_username}_{account_tag}":
                    account_key = account_puuid
                    conn.execute("""
                        INSERT OR REPLACE INTO henrik_accounts 
                        (account_key, username, tag, puuid, account_data, stored_at, last_accessed, data_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (account_key, account_username, account_tag, account_puuid, account_json, now, now, data_size))
                
                conn.commit()
                
                # Check if we need size-based cleanup
                self._check_and_cleanup_accounts(conn)
                
                return True
            
            except Exception as e:
                logging.error(f"Error storing account data: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def _check_and_cleanup_matches(self, conn, max_size_mb: int = 50) -> None:
        """Clean up old match data if storage exceeds size limit"""
        try:
            # Check total size
            size_row = conn.execute("SELECT SUM(data_size) as total_size FROM henrik_matches").fetchone()
            total_size_mb = (size_row['total_size'] or 0) / (1024 * 1024)
            
            if total_size_mb > max_size_mb:
                # Delete oldest accessed entries until we're under the limit
                target_size = max_size_mb * 0.8 * 1024 * 1024  # 80% of limit
                
                deleted = conn.execute("""
                    DELETE FROM henrik_matches WHERE match_id IN (
                        SELECT match_id FROM henrik_matches 
                        ORDER BY last_accessed ASC 
                        LIMIT (SELECT COUNT(*) / 4 FROM henrik_matches)
                    )
                """).rowcount
                
                if deleted > 0:
                    logging.info(f"Cleaned up {deleted} old match entries (size limit exceeded)")
                    
        except Exception as e:
            logging.error(f"Error during match cleanup: {e}")
    
    def _check_and_cleanup_player_stats(self, conn, max_size_mb: int = 20) -> None:
        """Clean up old player stats if storage exceeds size limit"""
        try:
            size_row = conn.execute("SELECT SUM(data_size) as total_size FROM henrik_player_stats").fetchone()
            total_size_mb = (size_row['total_size'] or 0) / (1024 * 1024)
            
            if total_size_mb > max_size_mb:
                deleted = conn.execute("""
                    DELETE FROM henrik_player_stats WHERE stats_key IN (
                        SELECT stats_key FROM henrik_player_stats 
                        ORDER BY last_accessed ASC 
                        LIMIT (SELECT COUNT(*) / 4 FROM henrik_player_stats)
                    )
                """).rowcount
                
                if deleted > 0:
                    logging.info(f"Cleaned up {deleted} old player stats entries (size limit exceeded)")
                    
        except Exception as e:
            logging.error(f"Error during player stats cleanup: {e}")
    
    def _check_and_cleanup_accounts(self, conn, max_size_mb: int = 5) -> None:
        """Clean up old account data if storage exceeds size limit"""
        try:
            size_row = conn.execute("SELECT SUM(data_size) as total_size FROM henrik_accounts").fetchone()
            total_size_mb = (size_row['total_size'] or 0) / (1024 * 1024)
            
            if total_size_mb > max_size_mb:
                deleted = conn.execute("""
                    DELETE FROM henrik_accounts WHERE account_key IN (
                        SELECT account_key FROM henrik_accounts 
                        ORDER BY last_accessed ASC 
                        LIMIT (SELECT COUNT(*) / 4 FROM henrik_accounts)
                    )
                """).rowcount
                
                if deleted > 0:
                    logging.info(f"Cleaned up {deleted} old account entries (size limit exceeded)")
                    
        except Exception as e:
            logging.error(f"Error during account cleanup: {e}")
    
    def get_henrik_storage_stats(self) -> Dict[str, Any]:
        """Get Henrik storage statistics"""
        with self._lock:
            conn = self._get_connection()
            try:
                stats = {}
                
                # Get counts and sizes for each table
                for table, name in [('henrik_matches', 'matches'), 
                                   ('henrik_player_stats', 'player_stats'), 
                                   ('henrik_accounts', 'accounts')]:
                    row = conn.execute(f"""
                        SELECT COUNT(*) as count, SUM(data_size) as total_size 
                        FROM {table}
                    """).fetchone()
                    
                    stats[f'stored_{name}'] = row['count']
                    stats[f'{name}_size_mb'] = (row['total_size'] or 0) / (1024 * 1024)
                
                return stats
            
            except Exception as e:
                logging.error(f"Error getting Henrik storage stats: {e}")
                return {}
            finally:
                conn.close()
    
    def clear_all_henrik_storage(self) -> bool:
        """Clear all Henrik storage data"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM henrik_matches")
                conn.execute("DELETE FROM henrik_player_stats")
                conn.execute("DELETE FROM henrik_accounts")
                
                conn.commit()
                logging.info("All Henrik storage cleared")
                return True
            
            except Exception as e:
                logging.error(f"Error clearing Henrik storage: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    # Match tracker state persistence methods
    def save_match_tracker_state(self, user_id: int, server_id: int, tracking_data: Dict[str, Any]) -> bool:
        """Save match tracker state for a user in a server"""
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
                logging.error(f"Error saving match tracker state for user {user_id}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def get_match_tracker_state(self, user_id: int, server_id: int) -> Optional[Dict[str, Any]]:
        """Get match tracker state for a user in a server"""
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
        """Get all tracked users for a server"""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT user_id, tracking_data FROM match_tracker_state 
                    WHERE server_id = ?
                """, (server_id,)).fetchall()
                
                tracked_users = {}
                for row in rows:
                    tracked_users[row['user_id']] = json.loads(row['tracking_data'])
                
                return tracked_users
            
            except Exception as e:
                logging.error(f"Error getting all tracked users for server {server_id}: {e}")
                return {}
            finally:
                conn.close()
    
    def save_stack_state(self, channel_id: int, has_played: bool = False, 
                        last_activity: Optional[datetime] = None, participant_count: int = 0) -> bool:
        """Save stack state for a channel"""
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
                        last_activity = COALESCE(?, last_activity),
                        participant_count = ?,
                        last_updated = ?
                """, (channel_id, has_played, last_activity_str, participant_count, now,
                      has_played, last_activity_str, participant_count, now))
                
                conn.commit()
                return True
            
            except Exception as e:
                logging.error(f"Error saving stack state for channel {channel_id}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def get_stack_state(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get stack state for a channel"""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("""
                    SELECT has_played, last_activity, participant_count, last_updated 
                    FROM stack_state WHERE channel_id = ?
                """, (channel_id,)).fetchone()
                
                if row:
                    last_activity = None
                    if row['last_activity']:
                        last_activity = datetime.fromisoformat(row['last_activity'])
                    
                    return {
                        'has_played': bool(row['has_played']),
                        'last_activity': last_activity,
                        'participant_count': row['participant_count'],
                        'last_updated': row['last_updated']
                    }
                return None
            
            except Exception as e:
                logging.error(f"Error getting stack state for channel {channel_id}: {e}")
                return None
            finally:
                conn.close()
    
    def get_all_stack_states(self) -> Dict[int, Dict[str, Any]]:
        """Get all stack states"""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT channel_id, has_played, last_activity, participant_count, last_updated 
                    FROM stack_state
                """).fetchall()
                
                stack_states = {}
                for row in rows:
                    last_activity = None
                    if row['last_activity']:
                        last_activity = datetime.fromisoformat(row['last_activity'])
                    
                    stack_states[row['channel_id']] = {
                        'has_played': bool(row['has_played']),
                        'last_activity': last_activity,
                        'participant_count': row['participant_count'],
                        'last_updated': row['last_updated']
                    }
                
                return stack_states
            
            except Exception as e:
                logging.error(f"Error getting all stack states: {e}")
                return {}
            finally:
                conn.close()
    
    def remove_match_tracker_state(self, user_id: int, server_id: int) -> bool:
        """Remove match tracker state for a user in a server"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    DELETE FROM match_tracker_state 
                    WHERE user_id = ? AND server_id = ?
                """, (user_id, server_id))
                
                conn.commit()
                return True
            
            except Exception as e:
                logging.error(f"Error removing match tracker state for user {user_id}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def remove_stack_state(self, channel_id: int) -> bool:
        """Remove stack state for a channel"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM stack_state WHERE channel_id = ?", (channel_id,))
                conn.commit()
                return True
            
            except Exception as e:
                logging.error(f"Error removing stack state for channel {channel_id}: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()
    
    def cleanup_old_tracker_state(self, days: int = 30) -> int:
        """Clean up old match tracker state data"""
        with self._lock:
            conn = self._get_connection()
            try:
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                
                # Remove old tracker states
                tracker_deleted = conn.execute("""
                    DELETE FROM match_tracker_state WHERE last_updated < ?
                """, (cutoff_date,)).rowcount
                
                # Remove old stack states  
                stack_deleted = conn.execute("""
                    DELETE FROM stack_state WHERE last_updated < ?
                """, (cutoff_date,)).rowcount
                
                conn.commit()
                
                total_deleted = tracker_deleted + stack_deleted
                if total_deleted > 0:
                    logging.info(f"Cleaned up {total_deleted} old tracker state entries (older than {days} days)")
                
                return total_deleted
            
            except Exception as e:
                logging.error(f"Error cleaning up old tracker state: {e}")
                conn.rollback()
                return 0
            finally:
                conn.close()


# Global database manager instance
database_manager = DatabaseManager()