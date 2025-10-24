import logging
import json
import os
from typing import Dict, Set, Optional, List, Any
from filelock import FileLock
import discord
from config import DEFAULT_SHOOTY_ROLE_CODE, DEFAULT_PARTY_SIZE, CHANNEL_DATA_FILE, DATA_DIR
from database import database_manager
from utils import ensure_directory_exists, log_error

class ShootyContext:
    """Manages the state for a single channel's party session"""
    
    def __init__(self, channel_id: int) -> None:
        self.channel_id: int = channel_id
        self.channel: Optional[discord.TextChannel] = None  # Discord channel object, set later

        # User sets
        self.bot_soloq_user_set: Set[str] = set()
        self.bot_fullstack_user_set: Set[str] = set()
        self.bot_ready_user_set: Set[str] = set()

        # Plus ones tracking (user_id -> number of guests)
        self.plus_ones: Dict[int, int] = {}

        # Message tracking
        self.current_st_message_id: Optional[int] = None

        # Channel settings
        self.role_code: str = DEFAULT_SHOOTY_ROLE_CODE
        self.game_name: Optional[str] = None
        self.party_max_size: int = DEFAULT_PARTY_SIZE
        self.voice_channel_id: Optional[int] = None

        # Backup for restore functionality
        self._backup: Optional[Dict[str, Any]] = None

        logging.info(f"Created ShootyContext for channel {channel_id}")
    
    def backup_state(self) -> None:
        """Backup current state for restore command"""
        self._backup = {
            'soloq': set(self.bot_soloq_user_set),
            'fullstack': set(self.bot_fullstack_user_set),
            'ready': set(self.bot_ready_user_set),
            'plus_ones': dict(self.plus_ones)
        }
        logging.info(f"Backed up state for channel {self.channel_id}")
    
    def restore_state(self) -> bool:
        """Restore from backup.

        Returns ``True`` if a backup was available and restored, ``False``
        otherwise.
        """
        if self._backup:
            self.bot_soloq_user_set = self._backup['soloq']
            self.bot_fullstack_user_set = self._backup['fullstack']
            self.bot_ready_user_set = self._backup['ready']
            self.plus_ones = self._backup.get('plus_ones', {})
            logging.info(f"Restored state for channel {self.channel_id}")
            return True
        else:
            logging.warning(f"No backup available for channel {self.channel_id}")
            return False
    
    def reset_users(self) -> None:
        """Clear all user sets"""
        self.bot_soloq_user_set.clear()
        self.bot_fullstack_user_set.clear()
        self.bot_ready_user_set.clear()
        self.plus_ones.clear()
    
    # Solo Q User Functions
    def get_soloq_user_count(self) -> int:
        """Get count of soloq users including their plus ones"""
        user_count = len(self.bot_soloq_user_set)
        # Add plus ones for soloq users only
        plus_ones_count = sum(
            self.get_plus_ones(user)
            for user in self.bot_soloq_user_set
        )
        return user_count + plus_ones_count

    def add_soloq_user(self, user: str) -> None:
        # Remove from fullstack if they were there
        self.bot_fullstack_user_set.discard(user)
        self.bot_soloq_user_set.add(user)
    
    def is_soloq_user(self, user: str) -> bool:
        return user in self.bot_soloq_user_set
    
    def remove_soloq_user(self, user: str) -> None:
        self.bot_soloq_user_set.discard(user)
    
    # Fullstack User Functions
    def get_fullstack_user_count(self) -> int:
        """Get count of fullstack users including their plus ones"""
        user_count = len(self.bot_fullstack_user_set)
        # Add plus ones for fullstack users only
        plus_ones_count = sum(
            self.get_plus_ones(user)
            for user in self.bot_fullstack_user_set
        )
        return user_count + plus_ones_count

    def add_fullstack_user(self, user: str) -> None:
        # Only add if they're not already in soloq
        if user not in self.bot_soloq_user_set:
            self.bot_fullstack_user_set.add(user)
    
    def remove_fullstack_user(self, user: str) -> None:
        self.bot_fullstack_user_set.discard(user)
    
    # Party Size Functions
    def set_party_max_size(self, size: int) -> None:
        self.party_max_size = size
    
    def get_party_max_size(self) -> int:
        return self.party_max_size

    # Plus Ones Functions
    def get_plus_ones(self, user) -> int:
        """Get number of plus ones for a user"""
        return self.plus_ones.get(user.id, 0)

    def set_plus_ones(self, user, count: int) -> None:
        """Set number of plus ones for a user"""
        if count <= 0:
            self.plus_ones.pop(user.id, None)
        else:
            self.plus_ones[user.id] = count

    def remove_plus_ones(self, user) -> None:
        """Remove all plus ones for a user"""
        self.plus_ones.pop(user.id, None)

    def get_total_plus_ones(self) -> int:
        """Get total number of plus ones across all users"""
        return sum(self.plus_ones.values())

    # Utility Functions
    def get_unique_user_count(self) -> int:
        """Get total party size including users and their plus ones"""
        user_count = len(self.bot_soloq_user_set.union(self.bot_fullstack_user_set))
        plus_ones_count = self.get_total_plus_ones()
        return user_count + plus_ones_count
    
    def remove_user_from_everything(self, user_names_list: List[str]) -> None:
        """Remove users by name prefix from all sets"""
        kicked_usernames_list = []

        for username in user_names_list:
            # Check soloq users
            for user in self.bot_soloq_user_set.copy():
                if user.name.startswith(username):
                    self.bot_soloq_user_set.remove(user)
                    # Also remove plus ones when user is kicked
                    self.remove_plus_ones(user)
                    kicked_usernames_list.append(user.name)

            # Check fullstack users
            for user in self.bot_fullstack_user_set.copy():
                if user.name.startswith(username):
                    self.bot_fullstack_user_set.remove(user)
                    # Also remove plus ones when user is kicked
                    self.remove_plus_ones(user)
                    kicked_usernames_list.append(user.name)

        return kicked_usernames_list
    
    # Formatting Functions
    def bold_readied_user(self, user: str, display_hashtag: bool = False) -> str:
        """Format username with bold if ready or in voice channel"""
        is_ready = user in self.bot_ready_user_set
        is_in_voice_channel = self._is_user_in_voice_channel(user)

        # Format name
        name = str(user) if display_hashtag else user.name

        # Add plus ones suffix if applicable
        plus_ones_count = self.get_plus_ones(user)
        if plus_ones_count > 0:
            name = f"{name}+{plus_ones_count}"

        # Apply formatting: bold if ready or in voice channel
        if is_in_voice_channel:
            return f"**{name}**"
        elif is_ready:
            return f"**{name}**"
        else:
            return name
    
    def _is_user_in_voice_channel(self, user) -> bool:
        """Check if user is in the configured voice channel"""
        if not self.voice_channel_id or not self.channel:
            return False
        
        try:
            # Get the voice channel
            voice_channel = self.channel.guild.get_channel(self.voice_channel_id)
            if not voice_channel:
                return False
            
            # Check if user is in the voice channel
            return user in voice_channel.members
        except Exception:
            return False
    
    def get_voice_channel_user_count(self) -> int:
        """Get count of users in the configured voice channel"""
        if not self.voice_channel_id or not self.channel:
            return 0
        
        try:
            # Get the voice channel
            voice_channel = self.channel.guild.get_channel(self.voice_channel_id)
            if not voice_channel:
                return 0
            
            # Return count of members in voice channel
            return len(voice_channel.members)
        except Exception:
            return 0
    
    def get_user_list_string(self) -> str:
        """Get formatted string of all users"""
        result_string = ""
        all_users_set = self.bot_soloq_user_set.union(self.bot_fullstack_user_set)
        
        for index, user in enumerate(all_users_set):
            if user in self.bot_fullstack_user_set and user not in self.bot_soloq_user_set:
                result_string += f"*{self.bold_readied_user(user)}*"
            else:
                result_string += self.bold_readied_user(user)
            
            if index < len(all_users_set) - 1:
                result_string += ", "
        
        return result_string
    
    def get_user_list_string_with_hashtag(self) -> str:
        """Get formatted string of all users with hashtags"""
        result_string = ""
        all_users_set = self.bot_soloq_user_set.union(self.bot_fullstack_user_set)
        
        for index, user in enumerate(all_users_set):
            if user in self.bot_fullstack_user_set and user not in self.bot_soloq_user_set:
                result_string += f"*{self.bold_readied_user(user, True)}*"
            else:
                result_string += self.bold_readied_user(user, True)
            
            if index < len(all_users_set) - 1:
                result_string += ", "
        
        return result_string
    
    # Persistence methods
    def to_dict(self) -> Dict[str, Any]:
        """Convert persistent data to dictionary for JSON storage"""
        return {
            'role_code': self.role_code,
            'game_name': self.game_name,
            'party_max_size': self.party_max_size,
            'voice_channel_id': self.voice_channel_id,
            'current_st_message_id': self.current_st_message_id
        }
    
    @classmethod
    def from_dict(cls, channel_id: int, data: Dict[str, Any]) -> 'ShootyContext':
        """Create context from dictionary data"""
        context = cls(channel_id)
        context.role_code = data.get('role_code', DEFAULT_SHOOTY_ROLE_CODE)
        context.game_name = data.get('game_name')
        context.party_max_size = data.get('party_max_size', DEFAULT_PARTY_SIZE)
        context.voice_channel_id = data.get('voice_channel_id')
        context.current_st_message_id = data.get('current_st_message_id')
        return context


class ContextManager:
    """Manages all ShootyContext instances and handles persistence"""
    
    def __init__(self) -> None:
        self.contexts = {}
        self.lock = FileLock(f"{CHANNEL_DATA_FILE}.lock")
        self.load_all_contexts()
    
    def get_context(self, channel_id: int) -> ShootyContext:
        """Get or create context for a channel"""
        if channel_id not in self.contexts:
            self.contexts[channel_id] = ShootyContext(channel_id)
            self.load_context_data(channel_id)
        
        return self.contexts[channel_id]
    
    def load_all_contexts(self) -> None:
        """Load all contexts from database (kept for compatibility)"""
        ensure_directory_exists(DATA_DIR)
        
        # Contexts are now loaded on-demand from database
        # This method is kept for compatibility
        logging.info("Using SQLite database for context storage")
    
    def load_context_data(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Load data for a specific context from database"""
        try:
            settings = database_manager.get_channel_settings(channel_id)
            if settings:
                context = self.contexts[channel_id]
                context.role_code = settings.get('role_code', DEFAULT_SHOOTY_ROLE_CODE)
                context.game_name = settings.get('game_name')
                context.party_max_size = settings.get('party_max_size', DEFAULT_PARTY_SIZE)
                context.voice_channel_id = settings.get('voice_channel_id')
                context.current_st_message_id = settings.get('current_st_message_id')
                logging.info(f"Loaded data for channel {channel_id} from database")
            else:
                logging.debug(f"No existing settings found for channel {channel_id}")
        except Exception as e:
            log_error(f"loading context data for {channel_id}", e)
    
    def save_context(self, channel_id: int) -> bool:
        """Save a specific context to database"""
        try:
            if channel_id in self.contexts:
                context = self.contexts[channel_id]
                success = database_manager.save_channel_settings(
                    channel_id,
                    context.role_code,
                    context.game_name,
                    context.party_max_size,
                    context.voice_channel_id,
                    context.current_st_message_id
                )
                if success:
                    logging.info(f"Saved context for channel {channel_id} to database")
                else:
                    logging.error(f"Failed to save context for channel {channel_id}")
        except Exception as e:
            log_error(f"saving context for {channel_id}", e)
    
    def save_all_contexts(self) -> None:
        """Save all active contexts to database."""
        saved_count = 0
        for channel_id in self.contexts:
            try:
                self.save_context(channel_id)
                saved_count += 1
            except Exception as e:
                log_error(f"saving context {channel_id} during save_all", e)
        logging.info(f"Saved {saved_count}/{len(self.contexts)} contexts")
    
    def _write_json_atomic(self, data: Dict[str, Any]) -> bool:
        """Write JSON data atomically (legacy method, kept for compatibility)"""
        # This method is no longer used but kept for compatibility
        pass


# Global context manager instance
context_manager = ContextManager()


def get_shooty_context_from_channel_id(channel_id: int) -> ShootyContext:
    """Helper function for backward compatibility"""
    return context_manager.get_context(channel_id)


def to_names_list(user_set: Set[str]) -> List[str]:
    """Helper function to convert user set to list of names"""
    return [user.name for user in user_set]