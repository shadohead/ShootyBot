import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Bot Information
APP_VERSION = "2.1.0"

# Discord Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
COMMAND_PREFIX = "$"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Default Settings
DEFAULT_PARTY_SIZE = 5
MAX_SCHEDULED_HOURS = 4

# Default role code (can be overridden per channel)
DEFAULT_SHOOTY_ROLE_CODE = os.getenv("SHOOTY_ROLE_CODE", "<@&773770148070424657>")

# Data Directory
DATA_DIR = os.getenv("DATA_DIR", "data")

# Henrik API Configuration
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY", "")

# Emojis (all in one place for easy modification)
EMOJI = {
    "THUMBS_UP": "👍",
    "FULL_STACK": "5️⃣", 
    "REFRESH": "🔄",
    "MENTION": "📣",
    "READY": "✅"
}

# Custom Emojis (server-specific)
CUSTOM_EMOJI = {
    "PARTY_FULL": "<:jettpog:724145370023591937>",
    "PARTY_EMPTY": "<:viper:725612569716326422>"
}

# Message Templates
MESSAGES = {
    "NO_ROLE": "First set the role for the bot to ping with ```$stsr <Role>```",
    "COMMAND_NOT_FOUND": "Command not found. Use *$shootyhelp* for list of commands.",
    "PARTY_EMPTY_SUFFIX": "sadge/{size} " + CUSTOM_EMOJI["PARTY_EMPTY"],
    "PARTY_FULL_SUFFIX": " " + CUSTOM_EMOJI["PARTY_FULL"],
    "NO_MEMBERS": "No shooty boys to mention.",
    "CLEARED_SESSION": "Cleared shooty session.",
    "RESTORED_SESSION": "Restoring shooty session to before it was cleared.",
    "PAST_TIME": "Shooty session cannot be scheduled in the past.",
    "TOO_FAR_FUTURE": "Shooty session can only be scheduled up to 4 hrs in advance.",
    "INVALID_TIME": "Must be a valid time. Try format HH:MM",
    "HELP_MESSAGE": "📖 For comprehensive help with all commands, use `/shootyhelp` (or try `/shootyhelp valorant`, `/shootyhelp admin`, `/shootyhelp reactions` for specific categories)",
    "NEED_GAME_NAME": "Set this channel's game name to see other queues with the same name ```$stsg <game name>```"
}

# File Paths
DATA_DIR = "data"
CHANNEL_DATA_FILE = os.path.join(DATA_DIR, "channel_data.json")

# Special Characters
DEFAULT_MSG = "‎"  # Invisible character for message formatting

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")