import logging
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from filelock import FileLock
from config import DATA_DIR
from database import database_manager
from utils import get_utc_timestamp, ensure_directory_exists, get_timestamp_string
from base_models import TimestampedModel, ValidatedModel, StatefulModel, DatabaseBackedManager

class UserData(TimestampedModel, ValidatedModel):
    """Represents a Discord user's persistent data"""
    
    def __init__(self, discord_id: int) -> None:
        TimestampedModel.__init__(self)
        ValidatedModel.__init__(self)
        self.discord_id = discord_id
        
        # Load data from database
        self._load_from_database()
        
        # Backward compatibility properties
        self._valorant_username = None
        self._valorant_tag = None
        self._valorant_puuid = None
        self._update_compatibility_properties()
    
    def _load_from_database(self) -> None:
        """Load user data from database"""
        data = database_manager.get_user(self.discord_id)
        if data:
            self.valorant_accounts = data.get('valorant_accounts', [])
            self.total_sessions = data.get('total_sessions', 0)
            self.total_games_played = data.get('total_games_played', 0)
            self.session_history = data.get('session_history', [])
            # Use existing timestamps if available
            if 'created_at' in data:
                self.created_at = data['created_at']
            if 'last_updated' in data:
                self.updated_at = data['last_updated']
        else:
            # Create new user in database
            database_manager.create_or_update_user(self.discord_id)
            self.valorant_accounts = []
            self.total_sessions = 0
            self.total_games_played = 0
            self.session_history = []
            # Timestamps already set by TimestampedModel.__init__()
    
    def _update_compatibility_properties(self) -> None:
        """Update backward compatibility properties from primary account"""
        primary_account = self.get_primary_account()
        if primary_account:
            self._valorant_username = primary_account['username']
            self._valorant_tag = primary_account['tag']
            self._valorant_puuid = primary_account['puuid']
        else:
            self._valorant_username = None
            self._valorant_tag = None
            self._valorant_puuid = None
    
    def link_valorant_account(self, username: str, tag: str, puuid: str, set_primary: bool = True) -> bool:
        """Link a Valorant account to this Discord user"""
        success = database_manager.link_valorant_account(
            self.discord_id, username, tag, puuid, set_primary
        )
        if success:
            self.update_timestamp()
            self._load_from_database()  # Refresh data from database
            self._update_compatibility_properties()
    
    def _set_primary_account(self, primary_account: dict) -> None:
        """Set an account as primary"""
        success = database_manager.link_valorant_account(
            self.discord_id, 
            primary_account['username'], 
            primary_account['tag'], 
            primary_account['puuid'], 
            True  # set_primary=True
        )
        if success:
            self.update_timestamp()
            self._load_from_database()  # Refresh data from database
            self._update_compatibility_properties()
    
    def remove_valorant_account(self, username: str, tag: str) -> bool:
        """Remove a specific Valorant account"""
        success = database_manager.remove_valorant_account(self.discord_id, username, tag)
        if success:
            self.update_timestamp()
            self._load_from_database()  # Refresh data from database
            self._update_compatibility_properties()
        return success
    
    def get_primary_account(self) -> Optional[Dict[str, str]]:
        """Get the primary Valorant account"""
        for account in self.valorant_accounts:
            if account.get('is_primary', account.get('primary', False)):
                return account
        return self.valorant_accounts[0] if self.valorant_accounts else None
    
    def get_all_accounts(self) -> List[Dict[str, str]]:
        """Get all Valorant accounts"""
        return self.valorant_accounts.copy()
    
    def set_primary_account(self, username: str, tag: str) -> bool:
        """Set a specific account as primary"""
        for account in self.valorant_accounts:
            if account['username'].lower() == username.lower() and account['tag'].lower() == tag.lower():
                success = database_manager.link_valorant_account(
                    self.discord_id, username, tag, 
                    account.get('puuid', ''), True
                )
                if success:
                    self.update_timestamp()
                    self._load_from_database()
                    self._update_compatibility_properties()
                return success
        return False
    
    # Backward compatibility properties
    @property
    def valorant_username(self):
        return self._valorant_username
    
    @valorant_username.setter
    def valorant_username(self, value):
        self._valorant_username = value
    
    @property
    def valorant_tag(self):
        return self._valorant_tag
    
    @valorant_tag.setter
    def valorant_tag(self, value):
        self._valorant_tag = value
    
    @property
    def valorant_puuid(self):
        return self._valorant_puuid
    
    @valorant_puuid.setter
    def valorant_puuid(self, value):
        self._valorant_puuid = value
    
    def increment_session_count(self):
        """Increment the total session count"""
        database_manager.increment_user_stats(self.discord_id, sessions=1)
        self.update_timestamp()
        self._load_from_database()  # Refresh data
    
    def increment_games_played(self):
        """Increment games played count"""
        database_manager.increment_user_stats(self.discord_id, games=1)
        self.update_timestamp()
        self._load_from_database()  # Refresh data
    
    def add_session_to_history(self, session_id: str):
        """Add a session ID to history"""
        # This is now handled automatically by the database when participants are added
        # Just refresh our data to get the latest session history
        self._load_from_database()
    
    def validate(self) -> bool:
        """Validate user data"""
        # Clear previous errors
        self.clear_validation_errors()
        
        # Validate discord_id
        if not isinstance(self.discord_id, int) or self.discord_id <= 0:
            self.add_validation_error("Invalid discord_id")
        
        # Validate valorant accounts
        for account in self.valorant_accounts:
            if not isinstance(account, dict):
                self.add_validation_error("Invalid valorant account format")
                continue
            if 'username' not in account or 'tag' not in account:
                self.add_validation_error("Valorant account missing username or tag")
        
        # Validate numeric fields
        if self.total_sessions < 0:
            self.add_validation_error("Total sessions cannot be negative")
        if self.total_games_played < 0:
            self.add_validation_error("Total games played cannot be negative")
        
        return len(self.get_validation_errors()) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility"""
        # Start with base class data (timestamps)
        data = super().to_dict()
        
        # Add user-specific data
        data.update({
            'discord_id': self.discord_id,
            'valorant_accounts': self.valorant_accounts,
            'total_sessions': self.total_sessions,
            'total_games_played': self.total_games_played,
            'session_history': self.session_history,
            'last_updated': self.updated_at,  # For backward compatibility
            # Backward compatibility
            'valorant_username': self.valorant_username,
            'valorant_tag': self.valorant_tag,
            'valorant_puuid': self.valorant_puuid
        })
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserData':
        """Create UserData from dictionary (for compatibility)"""
        # Simply create a new UserData instance, which will load from database
        # This method is kept for compatibility but data comes from database now
        return cls(data['discord_id'])


class SessionData(StatefulModel):
    """Represents a gaming session"""
    
    # Define valid states for a session
    VALID_STATES = ['active', 'completed', 'cancelled', 'expired']
    
    def __init__(self, session_id: str, channel_id: int = None, started_by: int = None):
        super().__init__(initial_state='active')
        self.session_id = session_id
        
        # Load data from database if it exists
        session_data = database_manager.get_session(session_id)
        if session_data:
            self.channel_id = session_data['channel_id']
            self.started_by = session_data['started_by']
            self.start_time = session_data['start_time']
            self.end_time = session_data['end_time']
            self.participants = session_data['participants']
            self.game_name = session_data['game_name']
            self.party_size = session_data['party_size']
            self.was_full = session_data['was_full']
            self.duration_minutes = session_data['duration_minutes']
            
            # Set timestamps from database
            if 'created_at' in session_data:
                self.created_at = session_data['created_at']
            else:
                self.created_at = self.start_time
            
            # Determine state based on end_time
            if self.end_time:
                self._state = 'completed'
        else:
            # Create new session
            if channel_id is not None and started_by is not None:
                self.channel_id = channel_id
                self.started_by = started_by
                self.start_time = get_utc_timestamp()
                self.created_at = self.start_time
                self.end_time = None
                self.participants = []
                self.game_name = None
                self.party_size = 5
                self.was_full = False
                self.duration_minutes = 0
                
                # Create in database
                database_manager.create_session(
                    session_id, channel_id, started_by, None, 5
                )
            else:
                raise ValueError("Session not found and insufficient data to create new session")
    
    def add_participant(self, discord_id: int):
        """Add a participant to the session"""
        success = database_manager.add_session_participant(self.session_id, discord_id)
        if success:
            self.update_timestamp()
            # Refresh data from database
            session_data = database_manager.get_session(self.session_id)
            if session_data:
                self.participants = session_data['participants']
                # Check if session is now full
                if len(self.participants) >= self.party_size:
                    self.was_full = True
    
    def end_session(self, final_state: str = 'completed'):
        """End the session and calculate duration

        Parameters
        ----------
        final_state: str, optional
            The state to mark the session with once ended. Defaults to
            ``'completed'``.
        """
        self.state = final_state  # Update state
        success = database_manager.end_session(self.session_id, self.was_full)
        if success:
            # Refresh data from database
            session_data = database_manager.get_session(self.session_id)
            if session_data:
                self.end_time = session_data['end_time']
                self.duration_minutes = session_data['duration_minutes']
    
    def cancel_session(self):
        """Cancel the session while recording its duration."""
        # Reuse end_session logic but keep the cancelled state
        self.end_session(final_state='cancelled')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility"""
        # Start with base class data (timestamps and state)
        data = super().to_dict()
        
        # Add session-specific data
        data.update({
            'session_id': self.session_id,
            'channel_id': self.channel_id,
            'started_by': self.started_by,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'participants': self.participants,
            'game_name': self.game_name,
            'party_size': self.party_size,
            'was_full': self.was_full,
            'duration_minutes': self.duration_minutes
        })
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionData':
        """Create SessionData from dictionary (for compatibility)"""
        # Simply create a new SessionData instance, which will load from database
        # This method is kept for compatibility but data comes from database now
        return cls(data['session_id'])


class DataManager(DatabaseBackedManager[UserData]):
    """Manages persistent data for users and sessions using SQLite database"""
    
    def __init__(self):
        super().__init__(table_name='users')
        
        # Legacy file paths for migration purposes
        self.users_file = os.path.join(DATA_DIR, "users.json")
        self.sessions_file = os.path.join(DATA_DIR, "sessions.json")
        
        # Additional cache for sessions (users are handled by base class)
        self.sessions = {}  # session_id -> SessionData
        
        self._ensure_data_dir()
        
        # Check if we need to migrate from JSON
        self._check_and_migrate_if_needed()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        ensure_directory_exists(DATA_DIR)
    
    def _check_and_migrate_if_needed(self):
        """Check if JSON files exist and SQLite database doesn't, then migrate"""
        db_path = os.path.join(DATA_DIR, "shooty_bot.db")
        
        # If database exists, we're already migrated
        if os.path.exists(db_path):
            logging.info("SQLite database found, using database storage")
            return
        
        # Check if JSON files exist for migration
        json_files_exist = (
            os.path.exists(self.users_file) or 
            os.path.exists(self.sessions_file) or
            os.path.exists(os.path.join(DATA_DIR, "channel_data.json"))
        )
        
        if json_files_exist:
            logging.warning("JSON files found but no SQLite database. Auto-migrating...")
            logging.warning("For manual migration with backup, use: python3 migrate_to_sqlite.py --backup")
            
            try:
                # Auto-migrate existing data
                success = database_manager.migrate_from_json(
                    self.users_file,
                    self.sessions_file,
                    os.path.join(DATA_DIR, "channel_data.json")
                )
                
                if success:
                    logging.info("Auto-migration completed successfully")
                    # Create backup of JSON files
                    backup_dir = os.path.join(DATA_DIR, f"json_backup_auto_{get_timestamp_string()}")
                    os.makedirs(backup_dir)
                    
                    for filename in ['users.json', 'sessions.json', 'channel_data.json']:
                        src_path = os.path.join(DATA_DIR, filename)
                        if os.path.exists(src_path):
                            dst_path = os.path.join(backup_dir, filename)
                            import shutil
                            shutil.copy2(src_path, dst_path)
                    
                    logging.info(f"JSON backup created at: {backup_dir}")
                else:
                    logging.error("Auto-migration failed. Please run migrate_to_sqlite.py manually")
            
            except Exception as e:
                logging.error(f"Auto-migration error: {e}")
                logging.error("Please run migrate_to_sqlite.py manually")
        else:
            logging.info("No existing data found, starting with fresh SQLite database")
    
    def load_all_data(self):
        """Load all user and session data (kept for compatibility)"""
        # Data is now loaded on-demand from database
        # This method is kept for compatibility but doesn't need to do anything
        logging.info("Using SQLite database for data storage")
    
    # Implement abstract methods from DatabaseBackedManager
    def get(self, discord_id: int) -> Optional[UserData]:
        """Get user data from cache or database"""
        if discord_id in self._cache:
            return self._cache[discord_id]
        
        # Try to load from database
        if self._exists_in_storage(discord_id):
            user = UserData(discord_id)
            self._cache[discord_id] = user
            return user
        
        return None
    
    def create(self, discord_id: int, **kwargs) -> UserData:
        """Create a new user"""
        user = UserData(discord_id)
        self._cache[discord_id] = user
        return user
    
    def save(self, discord_id: int) -> bool:
        """Save user data (automatic with database)"""
        # Data is automatically saved to database
        # Just remove from modified set
        self._modified.discard(discord_id)
        return True
    
    def delete(self, discord_id: int) -> bool:
        """Delete a user"""
        # Remove from cache
        if discord_id in self._cache:
            del self._cache[discord_id]
        
        # Database doesn't have a delete_user method yet
        # For now, return True as we removed from cache
        self._modified.discard(discord_id)
        return True
    
    def _exists_in_storage(self, discord_id: int) -> bool:
        """Check if user exists in database"""
        return self.db.get_user(discord_id) is not None
    
    # Legacy method for compatibility
    def get_user(self, discord_id: int) -> UserData:
        """Get or create user data"""
        user = self.get(discord_id)
        if user is None:
            user = self.create(discord_id)
        return user
    
    def save_user(self, discord_id: int):
        """Save a specific user's data (automatic with database)"""
        # Delegate to base class save method
        self.save(discord_id)
        logging.debug(f"User data for {discord_id} is automatically saved to database")
    
    def create_session(self, channel_id: int, started_by: int, game_name: str = None) -> SessionData:
        """Create a new session"""
        session_id = f"{channel_id}_{int(datetime.now(timezone.utc).timestamp())}"
        session = SessionData(session_id, channel_id, started_by)
        
        # Update game name if provided
        if game_name:
            session.game_name = game_name
            # Note: Game name update in database would need additional database method
        
        self.sessions[session_id] = session
        return session
    
    def save_session(self, session_id: str):
        """Save a specific session's data (automatic with database)"""
        # Data is automatically saved to database when methods are called
        # This method is kept for compatibility but doesn't need to do anything
        logging.debug(f"Session data for {session_id} is automatically saved to database")
    
    def get_user_sessions(self, discord_id: int, limit: int = 10) -> List[SessionData]:
        """Get recent sessions for a user"""
        sessions_data = database_manager.get_user_sessions(discord_id, limit)
        return [SessionData(session['session_id']) for session in sessions_data]
    
    def get_channel_sessions(self, channel_id: int, limit: int = 10) -> List[SessionData]:
        """Get recent sessions for a channel"""
        sessions_data = database_manager.get_channel_sessions(channel_id, limit)
        return [SessionData(session['session_id']) for session in sessions_data]
    


# Global data manager instance
data_manager = DataManager()