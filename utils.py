"""Common utilities for ShootyBot."""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Union, Optional, Any, Dict, Callable, Awaitable, TypeVar
import discord
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


def parse_henrik_timestamp(value: Any) -> Optional[datetime]:
    """Parse a Henrik API timestamp which may be ISO8601 or UNIX epoch."""
    if value is None or value == "":
        return None

    try:
        # If numeric (or numeric string), treat as epoch seconds or ms
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = float(value)
            if ts > 1e12:  # likely milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)

        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as e:
        logging.debug(f"Failed to parse timestamp {value}: {e}")

    return None


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


# Discord Utilities
def format_role_mention(role_id: int) -> str:
    """Format role ID as Discord mention."""
    return f"<@&{role_id}>"


def resolve_role(guild: discord.Guild, role_input: str) -> Optional[discord.Role]:
    """Resolve a guild role from a mention, ID, or name."""
    if not role_input:
        return None

    cleaned = role_input.strip()
    role_id = None

    if cleaned.startswith("<@&") and cleaned.endswith(">"):
        try:
            role_id = int(cleaned[3:-1])
        except ValueError:
            pass
    elif cleaned.isdigit():
        role_id = int(cleaned)

    role: Optional[discord.Role] = None
    if role_id is not None:
        role = guild.get_role(role_id)

    if role is None:
        role = discord.utils.get(guild.roles, name=cleaned)

    return role


def resolve_voice_channel(
    guild: discord.Guild, channel_input: str
) -> Optional[discord.VoiceChannel]:
    """Resolve a voice channel from a mention, ID, or name."""
    if not channel_input:
        return None

    cleaned = channel_input.strip()
    channel_id = None

    if cleaned.startswith("<#") and cleaned.endswith(">"):
        try:
            channel_id = int(cleaned[2:-1])
        except ValueError:
            pass
    elif cleaned.isdigit():
        channel_id = int(cleaned)

    channel = None
    if channel_id is not None:
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            channel = None

    if channel is None:
        channel = discord.utils.get(guild.voice_channels, name=cleaned)

    return channel


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


