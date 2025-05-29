import logging
import json
import os
from filelock import FileLock
from config import *
from database import database_manager

class ShootyContext:
    """Manages the state for a single channel's party session"""
    
    def __init__(self, channel_id):
        self.channel_id = channel_id
        self.channel = None  # Discord channel object, set later
        
        # User sets
        self.bot_soloq_user_set = set()
        self.bot_fullstack_user_set = set()
        self.bot_ready_user_set = set()
        
        # Message tracking
        self.current_st_message_id = None
        
        # Channel settings
        self.role_code = DEFAULT_SHOOTY_ROLE_CODE
        self.game_name = None
        self.party_max_size = DEFAULT_PARTY_SIZE
        
        # Backup for restore functionality
        self._backup = None
        
        logging.info(f"Created ShootyContext for channel {channel_id}")
    
    def backup_state(self):
        """Backup current state for restore command"""
        self._backup = {
            'soloq': set(self.bot_soloq_user_set),
            'fullstack': set(self.bot_fullstack_user_set),
            'ready': set(self.bot_ready_user_set)
        }
        logging.info(f"Backed up state for channel {self.channel_id}")
    
    def restore_state(self):
        """Restore from backup"""
        if self._backup:
            self.bot_soloq_user_set = self._backup['soloq']
            self.bot_fullstack_user_set = self._backup['fullstack']
            self.bot_ready_user_set = self._backup['ready']
            logging.info(f"Restored state for channel {self.channel_id}")
        else:
            logging.warning(f"No backup available for channel {self.channel_id}")
    
    def reset_users(self):
        """Clear all user sets"""
        self.bot_soloq_user_set.clear()
        self.bot_fullstack_user_set.clear()
        self.bot_ready_user_set.clear()
    
    # Solo Q User Functions
    def get_soloq_user_count(self):
        return len(self.bot_soloq_user_set)
    
    def add_soloq_user(self, user):
        # Remove from fullstack if they were there
        self.bot_fullstack_user_set.discard(user)
        self.bot_soloq_user_set.add(user)
    
    def is_soloq_user(self, user):
        return user in self.bot_soloq_user_set
    
    def remove_soloq_user(self, user):
        self.bot_soloq_user_set.discard(user)
    
    # Fullstack User Functions
    def get_fullstack_user_count(self):
        return len(self.bot_fullstack_user_set)
    
    def add_fullstack_user(self, user):
        # Only add if they're not already in soloq
        if user not in self.bot_soloq_user_set:
            self.bot_fullstack_user_set.add(user)
    
    def remove_fullstack_user(self, user):
        self.bot_fullstack_user_set.discard(user)
    
    # Party Size Functions
    def set_party_max_size(self, size):
        self.party_max_size = size
    
    def get_party_max_size(self):
        return self.party_max_size
    
    # Utility Functions
    def get_unique_user_count(self):
        return len(self.bot_soloq_user_set.union(self.bot_fullstack_user_set))
    
    def remove_user_from_everything(self, user_names_list):
        """Remove users by name prefix from all sets"""
        kicked_usernames_list = []
        
        for username in user_names_list:
            # Check soloq users
            for user in self.bot_soloq_user_set.copy():
                if user.name.startswith(username):
                    self.bot_soloq_user_set.remove(user)
                    kicked_usernames_list.append(user.name)
            
            # Check fullstack users
            for user in self.bot_fullstack_user_set.copy():
                if user.name.startswith(username):
                    self.bot_fullstack_user_set.remove(user)
                    kicked_usernames_list.append(user.name)
        
        return kicked_usernames_list
    
    # Formatting Functions
    def bold_readied_user(self, user, display_hashtag=False):
        """Format username with bold if ready or playing Valorant"""
        from valorant_client import valorant_client
        
        is_ready = user in self.bot_ready_user_set
        is_playing_valorant = valorant_client.is_playing_valorant(user)
        
        # Format name
        name = str(user) if display_hashtag else user.name
        
        # Apply formatting: bold if ready, double bold if playing Valorant
        if is_playing_valorant:
            return f"**{name}** 🎮"
        elif is_ready:
            return f"**{name}**"
        else:
            return name
    
    def get_user_list_string(self):
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
    
    def get_user_list_string_with_hashtag(self):
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
    def to_dict(self):
        """Convert persistent data to dictionary for JSON storage"""
        return {
            'role_code': self.role_code,
            'game_name': self.game_name,
            'party_max_size': self.party_max_size
        }
    
    @classmethod
    def from_dict(cls, channel_id, data):
        """Create context from dictionary data"""
        context = cls(channel_id)
        context.role_code = data.get('role_code', DEFAULT_SHOOTY_ROLE_CODE)
        context.game_name = data.get('game_name')
        context.party_max_size = data.get('party_max_size', DEFAULT_PARTY_SIZE)
        return context


class ContextManager:
    """Manages all ShootyContext instances and handles persistence"""
    
    def __init__(self):
        self.contexts = {}
        self.lock = FileLock(f"{CHANNEL_DATA_FILE}.lock")
        self.load_all_contexts()
    
    def get_context(self, channel_id):
        """Get or create context for a channel"""
        if channel_id not in self.contexts:
            self.contexts[channel_id] = ShootyContext(channel_id)
            self.load_context_data(channel_id)
        
        return self.contexts[channel_id]
    
    def load_all_contexts(self):
        """Load all contexts from database (kept for compatibility)"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        
        # Contexts are now loaded on-demand from database
        # This method is kept for compatibility
        logging.info("Using SQLite database for context storage")
    
    def load_context_data(self, channel_id):
        """Load data for a specific context from database"""
        try:
            settings = database_manager.get_channel_settings(channel_id)
            if settings:
                context = self.contexts[channel_id]
                context.role_code = settings.get('role_code', DEFAULT_SHOOTY_ROLE_CODE)
                context.game_name = settings.get('game_name')
                context.party_max_size = settings.get('party_max_size', DEFAULT_PARTY_SIZE)
                logging.info(f"Loaded data for channel {channel_id} from database")
            else:
                logging.debug(f"No existing settings found for channel {channel_id}")
        except Exception as e:
            logging.error(f"Error loading context data for {channel_id}: {e}")
    
    def save_context(self, channel_id):
        """Save a specific context to database"""
        try:
            if channel_id in self.contexts:
                context = self.contexts[channel_id]
                success = database_manager.save_channel_settings(
                    channel_id,
                    context.role_code,
                    context.game_name,
                    context.party_max_size
                )
                if success:
                    logging.info(f"Saved context for channel {channel_id} to database")
                else:
                    logging.error(f"Failed to save context for channel {channel_id}")
        except Exception as e:
            logging.error(f"Error saving context for {channel_id}: {e}")
    
    def _write_json_atomic(self, data):
        """Write JSON data atomically (legacy method, kept for compatibility)"""
        # This method is no longer used but kept for compatibility
        pass


# Global context manager instance
context_manager = ContextManager()


def get_shooty_context_from_channel_id(channel_id):
    """Helper function for backward compatibility"""
    return context_manager.get_context(channel_id)


def to_names_list(user_set):
    """Helper function to convert user set to list of names"""
    return [user.name for user in user_set]