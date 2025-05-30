import sqlite3
import logging
import os
import json
from datetime import datetime, timezone
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
                
                # Create indexes for better query performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_valorant_accounts_discord_id ON valorant_accounts(discord_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_valorant_accounts_primary ON valorant_accounts(discord_id, is_primary)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_channel_id ON sessions(channel_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_started_by ON sessions(started_by)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session_participants_session_id ON session_participants(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session_participants_discord_id ON session_participants(discord_id)")
                
                conn.commit()
                logging.info("Database tables initialized successfully")
            
            except Exception as e:
                conn.rollback()
                logging.error(f"Error initializing database: {e}")
                raise
            finally:
                conn.close()
    
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
                
                # Ensure user exists
                self.create_or_update_user(discord_id)
                
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
                
                tables = ['users', 'valorant_accounts', 'sessions', 'session_participants', 'channel_settings']
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


# Global database manager instance
database_manager = DatabaseManager()