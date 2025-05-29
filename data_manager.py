import logging
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from filelock import FileLock
from config import DATA_DIR

class UserData:
    """Represents a Discord user's persistent data"""
    
    def __init__(self, discord_id: int):
        self.discord_id = discord_id
        self.valorant_accounts = []  # List of dict: {'username': str, 'tag': str, 'puuid': str, 'primary': bool}
        self.total_sessions = 0
        self.total_games_played = 0
        self.session_history = []  # List of session IDs
        self.last_updated = datetime.now(timezone.utc).isoformat()
        
        # Backward compatibility properties
        self._valorant_username = None
        self._valorant_tag = None
        self._valorant_puuid = None
    
    def link_valorant_account(self, username: str, tag: str, puuid: str, set_primary: bool = True):
        """Link a Valorant account to this Discord user"""
        # Check if account already exists
        for account in self.valorant_accounts:
            if account['username'].lower() == username.lower() and account['tag'].lower() == tag.lower():
                # Update existing account
                account['puuid'] = puuid
                if set_primary:
                    self._set_primary_account(account)
                self.last_updated = datetime.now(timezone.utc).isoformat()
                return
        
        # If setting as primary, unmark other primary accounts
        if set_primary:
            for account in self.valorant_accounts:
                account['primary'] = False
        
        # Add new account
        new_account = {
            'username': username,
            'tag': tag,
            'puuid': puuid,
            'primary': set_primary or len(self.valorant_accounts) == 0
        }
        self.valorant_accounts.append(new_account)
        
        # Backward compatibility
        if new_account['primary']:
            self._valorant_username = username
            self._valorant_tag = tag
            self._valorant_puuid = puuid
        
        self.last_updated = datetime.now(timezone.utc).isoformat()
    
    def _set_primary_account(self, primary_account: dict):
        """Set an account as primary"""
        for account in self.valorant_accounts:
            account['primary'] = (account == primary_account)
        
        # Update backward compatibility properties
        self._valorant_username = primary_account['username']
        self._valorant_tag = primary_account['tag']
        self._valorant_puuid = primary_account['puuid']
    
    def remove_valorant_account(self, username: str, tag: str) -> bool:
        """Remove a specific Valorant account"""
        for i, account in enumerate(self.valorant_accounts):
            if account['username'].lower() == username.lower() and account['tag'].lower() == tag.lower():
                was_primary = account['primary']
                del self.valorant_accounts[i]
                
                # If removed account was primary, set first remaining as primary
                if was_primary and self.valorant_accounts:
                    self.valorant_accounts[0]['primary'] = True
                    self._valorant_username = self.valorant_accounts[0]['username']
                    self._valorant_tag = self.valorant_accounts[0]['tag']
                    self._valorant_puuid = self.valorant_accounts[0]['puuid']
                elif not self.valorant_accounts:
                    # No accounts left
                    self._valorant_username = None
                    self._valorant_tag = None
                    self._valorant_puuid = None
                
                self.last_updated = datetime.now(timezone.utc).isoformat()
                return True
        return False
    
    def get_primary_account(self) -> Optional[Dict[str, str]]:
        """Get the primary Valorant account"""
        for account in self.valorant_accounts:
            if account['primary']:
                return account
        return self.valorant_accounts[0] if self.valorant_accounts else None
    
    def get_all_accounts(self) -> List[Dict[str, str]]:
        """Get all Valorant accounts"""
        return self.valorant_accounts.copy()
    
    def set_primary_account(self, username: str, tag: str) -> bool:
        """Set a specific account as primary"""
        for account in self.valorant_accounts:
            if account['username'].lower() == username.lower() and account['tag'].lower() == tag.lower():
                self._set_primary_account(account)
                self.last_updated = datetime.now(timezone.utc).isoformat()
                return True
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
        self.total_sessions += 1
        self.last_updated = datetime.now(timezone.utc).isoformat()
    
    def increment_games_played(self):
        """Increment games played count"""
        self.total_games_played += 1
        self.last_updated = datetime.now(timezone.utc).isoformat()
    
    def add_session_to_history(self, session_id: str):
        """Add a session ID to history"""
        if session_id not in self.session_history:
            self.session_history.append(session_id)
            self.last_updated = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
            'discord_id': self.discord_id,
            'valorant_accounts': self.valorant_accounts,
            'total_sessions': self.total_sessions,
            'total_games_played': self.total_games_played,
            'session_history': self.session_history,
            'last_updated': self.last_updated,
            # Backward compatibility
            'valorant_username': self.valorant_username,
            'valorant_tag': self.valorant_tag,
            'valorant_puuid': self.valorant_puuid
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserData':
        """Create UserData from dictionary"""
        user = cls(data['discord_id'])
        
        # Handle new format with multiple accounts
        if 'valorant_accounts' in data:
            user.valorant_accounts = data.get('valorant_accounts', [])
            
            # Set backward compatibility properties from primary account
            primary_account = user.get_primary_account()
            if primary_account:
                user._valorant_username = primary_account['username']
                user._valorant_tag = primary_account['tag']
                user._valorant_puuid = primary_account['puuid']
        else:
            # Handle old format - migrate to new format
            old_username = data.get('valorant_username')
            old_tag = data.get('valorant_tag')
            old_puuid = data.get('valorant_puuid')
            
            if old_username and old_tag:
                user.valorant_accounts = [{
                    'username': old_username,
                    'tag': old_tag,
                    'puuid': old_puuid or f"legacy_{old_username}_{old_tag}",
                    'primary': True
                }]
                user._valorant_username = old_username
                user._valorant_tag = old_tag
                user._valorant_puuid = old_puuid
        
        user.total_sessions = data.get('total_sessions', 0)
        user.total_games_played = data.get('total_games_played', 0)
        user.session_history = data.get('session_history', [])
        user.last_updated = data.get('last_updated', datetime.now(timezone.utc).isoformat())
        return user


class SessionData:
    """Represents a gaming session"""
    
    def __init__(self, session_id: str, channel_id: int, started_by: int):
        self.session_id = session_id
        self.channel_id = channel_id
        self.started_by = started_by
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.end_time = None
        self.participants = []  # List of discord_ids
        self.game_name = None
        self.party_size = 5
        self.was_full = False
        self.duration_minutes = 0
    
    def add_participant(self, discord_id: int):
        """Add a participant to the session"""
        if discord_id not in self.participants:
            self.participants.append(discord_id)
    
    def end_session(self):
        """End the session and calculate duration"""
        self.end_time = datetime.now(timezone.utc).isoformat()
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        self.duration_minutes = int((end - start).total_seconds() / 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
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
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionData':
        """Create SessionData from dictionary"""
        session = cls(data['session_id'], data['channel_id'], data['started_by'])
        session.start_time = data['start_time']
        session.end_time = data.get('end_time')
        session.participants = data.get('participants', [])
        session.game_name = data.get('game_name')
        session.party_size = data.get('party_size', 5)
        session.was_full = data.get('was_full', False)
        session.duration_minutes = data.get('duration_minutes', 0)
        return session


class DataManager:
    """Manages persistent data for users and sessions"""
    
    def __init__(self):
        self.users_file = os.path.join(DATA_DIR, "users.json")
        self.sessions_file = os.path.join(DATA_DIR, "sessions.json")
        self.users_lock = FileLock(f"{self.users_file}.lock")
        self.sessions_lock = FileLock(f"{self.sessions_file}.lock")
        
        self.users = {}  # discord_id -> UserData
        self.sessions = {}  # session_id -> SessionData
        
        self._ensure_data_dir()
        self.load_all_data()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
    
    def load_all_data(self):
        """Load all user and session data"""
        self._load_users()
        self._load_sessions()
    
    def _load_users(self):
        """Load user data from JSON file"""
        if os.path.exists(self.users_file):
            try:
                with self.users_lock:
                    with open(self.users_file, 'r') as f:
                        data = json.load(f)
                
                for discord_id, user_data in data.items():
                    self.users[int(discord_id)] = UserData.from_dict(user_data)
                
                logging.info(f"Loaded {len(self.users)} users from file")
            except Exception as e:
                logging.error(f"Error loading users: {e}")
        else:
            logging.info("No existing users data file found")
    
    def _load_sessions(self):
        """Load session data from JSON file"""
        if os.path.exists(self.sessions_file):
            try:
                with self.sessions_lock:
                    with open(self.sessions_file, 'r') as f:
                        data = json.load(f)
                
                for session_id, session_data in data.items():
                    self.sessions[session_id] = SessionData.from_dict(session_data)
                
                logging.info(f"Loaded {len(self.sessions)} sessions from file")
            except Exception as e:
                logging.error(f"Error loading sessions: {e}")
        else:
            logging.info("No existing sessions data file found")
    
    def get_user(self, discord_id: int) -> UserData:
        """Get or create user data"""
        if discord_id not in self.users:
            self.users[discord_id] = UserData(discord_id)
        return self.users[discord_id]
    
    def save_user(self, discord_id: int):
        """Save a specific user's data"""
        try:
            with self.users_lock:
                # Read current data
                data = {}
                if os.path.exists(self.users_file):
                    with open(self.users_file, 'r') as f:
                        data = json.load(f)
                
                # Update specific user
                if discord_id in self.users:
                    data[str(discord_id)] = self.users[discord_id].to_dict()
                
                # Write atomically
                self._write_json_atomic(self.users_file, data)
                logging.info(f"Saved user data for {discord_id}")
        except Exception as e:
            logging.error(f"Error saving user {discord_id}: {e}")
    
    def create_session(self, channel_id: int, started_by: int, game_name: str = None) -> SessionData:
        """Create a new session"""
        session_id = f"{channel_id}_{int(datetime.now(timezone.utc).timestamp())}"
        session = SessionData(session_id, channel_id, started_by)
        session.game_name = game_name
        self.sessions[session_id] = session
        return session
    
    def save_session(self, session_id: str):
        """Save a specific session's data"""
        try:
            with self.sessions_lock:
                # Read current data
                data = {}
                if os.path.exists(self.sessions_file):
                    with open(self.sessions_file, 'r') as f:
                        data = json.load(f)
                
                # Update specific session
                if session_id in self.sessions:
                    data[session_id] = self.sessions[session_id].to_dict()
                
                # Write atomically
                self._write_json_atomic(self.sessions_file, data)
                logging.info(f"Saved session data for {session_id}")
        except Exception as e:
            logging.error(f"Error saving session {session_id}: {e}")
    
    def get_user_sessions(self, discord_id: int, limit: int = 10) -> List[SessionData]:
        """Get recent sessions for a user"""
        user_sessions = []
        for session in self.sessions.values():
            if discord_id in session.participants:
                user_sessions.append(session)
        
        # Sort by start time, most recent first
        user_sessions.sort(key=lambda s: s.start_time, reverse=True)
        return user_sessions[:limit]
    
    def get_channel_sessions(self, channel_id: int, limit: int = 10) -> List[SessionData]:
        """Get recent sessions for a channel"""
        channel_sessions = []
        for session in self.sessions.values():
            if session.channel_id == channel_id:
                channel_sessions.append(session)
        
        # Sort by start time, most recent first
        channel_sessions.sort(key=lambda s: s.start_time, reverse=True)
        return channel_sessions[:limit]
    
    def _write_json_atomic(self, file_path: str, data: Dict):
        """Write JSON data atomically to prevent corruption"""
        temp_file = f"{file_path}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, file_path)
        except Exception as e:
            # Clean up temp file if something went wrong
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise e


# Global data manager instance
data_manager = DataManager()