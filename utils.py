"""Common utilities for ShootyBot."""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Union, Optional, Any, Dict, Callable, Awaitable, TypeVar
import discord
import sqlite3
from filelock import FileLock
import asyncio
from functools import wraps


# Time Utilities
def get_utc_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def get_timestamp_string() -> str:
    """Get timestamp string for file names (YYYYMMDD_HHMMSS)."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def format_time_for_display(dt: datetime, format_str: str = '%I:%M %p') -> str:
    """Format datetime for user display."""
    return dt.strftime(format_str)


def format_time_ago(dt: datetime) -> str:
    """Format datetime as 'X minutes/hours/days ago'."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "just now"


# File/Directory Utilities
def ensure_directory_exists(path: str) -> None:
    """Ensure directory exists, create if it doesn't."""
    if not os.path.exists(path):
        os.makedirs(path)
        logging.info(f"Created directory: {path}")


def safe_json_load(filepath: str, default: Any = None) -> Any:
    """Load JSON file with error handling."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.debug(f"File not found: {filepath}, returning default")
        return default
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error in {filepath}: {e}")
        return default
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return default


def safe_json_save(filepath: str, data: Any, indent: int = 2) -> bool:
    """Save JSON file with atomic write and error handling."""
    try:
        # Write to temp file first
        temp_file = f"{filepath}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=indent)
        
        # Atomic rename
        os.replace(temp_file, filepath)
        return True
    except Exception as e:
        logging.error(f"Error saving {filepath}: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False


def atomic_json_operation(filepath: str, operation: Callable, default: Any = None) -> Any:
    """Perform atomic JSON read-modify-write operation with file locking."""
    lock_file = f"{filepath}.lock"
    lock = FileLock(lock_file, timeout=10)
    
    try:
        with lock:
            # Load current data
            data = safe_json_load(filepath, default)
            
            # Perform operation
            result = operation(data)
            
            # Save if data was modified
            if result is not None:
                safe_json_save(filepath, result)
                return result
            return data
    except Exception as e:
        logging.error(f"Atomic operation failed on {filepath}: {e}")
        return default


# Discord Utilities
def get_display_name(member_or_user: Union[discord.Member, discord.User]) -> str:
    """Get appropriate display name for Discord member or user."""
    if isinstance(member_or_user, discord.Member):
        return member_or_user.display_name
    return member_or_user.name


def format_user_mention(user_id: int) -> str:
    """Format user ID as Discord mention."""
    return f"<@{user_id}>"


def format_role_mention(role_id: int) -> str:
    """Format role ID as Discord mention."""
    return f"<@&{role_id}>"


def format_channel_mention(channel_id: int) -> str:
    """Format channel ID as Discord mention."""
    return f"<#{channel_id}>"


def safe_embed_field(embed: discord.Embed, name: str, value: str, inline: bool = True) -> None:
    """Add field to embed with length validation."""
    # Discord limits: name=256, value=1024
    if len(name) > 256:
        name = name[:253] + "..."
    if len(value) > 1024:
        value = value[:1021] + "..."
    
    embed.add_field(name=name, value=value, inline=inline)


# Error Handling Utilities
def log_error(action: str, error: Exception, level: int = logging.ERROR) -> None:
    """Standardized error logging."""
    logging.log(level, f"Error {action}: {type(error).__name__}: {str(error)}")


def handle_api_error(error: Exception, default: Any = None) -> Any:
    """Handle API errors with appropriate logging and default return."""
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        status_code = error.response.status_code
        if status_code == 429:
            logging.warning(f"Rate limited: {error}")
        elif status_code == 404:
            logging.debug(f"Not found: {error}")
        elif status_code >= 500:
            logging.error(f"Server error: {error}")
        else:
            logging.error(f"API error {status_code}: {error}")
    else:
        logging.error(f"API error: {error}")
    
    return default


# Database Utilities
def get_db_connection(db_path: str, timeout: float = 30.0) -> sqlite3.Connection:
    """Get SQLite connection with standard settings."""
    conn = sqlite3.connect(db_path, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def execute_with_retry(func: Callable, max_retries: int = 3, delay: float = 0.1) -> Any:
    """Execute function with exponential backoff retry."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            last_error = e
            if "database is locked" in str(e) and attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)
                logging.warning(f"Database locked, retrying in {wait_time}s...")
                asyncio.sleep(wait_time)
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                logging.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                asyncio.sleep(delay)
            else:
                raise
    
    raise last_error


# Async Utilities
F = TypeVar('F', bound=Callable[..., Awaitable[Any]])

def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0) -> Callable[[F], F]:
    """Decorator for async functions with retry logic."""
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            wait_time = delay
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logging.warning(f"{func.__name__} attempt {attempt + 1} failed: {e}")
                        await asyncio.sleep(wait_time)
                        wait_time *= backoff
                    else:
                        raise
            
            raise last_error
        return wrapper  # type: ignore
    return decorator


# Validation Utilities
def validate_discord_id(discord_id: Any) -> Optional[int]:
    """Validate and convert Discord ID to int."""
    try:
        id_int = int(discord_id)
        if id_int > 0:
            return id_int
    except (ValueError, TypeError):
        pass
    return None


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize filename for safe file system usage."""
    # Remove/replace invalid characters
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Limit length
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        name = name[:max_length - len(ext) - 3] + '...'
        filename = name + ext
    
    return filename or 'unnamed'


# String Utilities
def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to max length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Return singular or plural form based on count."""
    if count == 1:
        return singular
    return plural or f"{singular}s"
