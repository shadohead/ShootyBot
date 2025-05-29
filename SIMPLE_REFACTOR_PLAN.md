# ShootyBot Simple Refactor Plan

## Philosophy
Keep it simple, improve what matters, don't over-engineer.

## Current Pain Points
1. Everything in one file (495 lines is getting unwieldy)
2. JSON file corruption risk (no atomic writes)
3. Hard-coded values scattered everywhere
4. Reaction handling is getting complex

## Proposed Simple Structure
```
ShootyBot/
├── bot.py                    # Main bot file (150-200 lines)
├── config.py                 # All configuration in one place
├── context_manager.py        # ShootyContext and persistence
├── commands/
│   ├── __init__.py
│   ├── session_commands.py   # st, sts, stm commands
│   ├── party_commands.py     # shootysize, shootykick, etc.
│   └── admin_commands.py     # shootysetrole, shootysetgame
├── handlers/
│   ├── __init__.py
│   ├── reaction_handler.py   # All reaction logic
│   └── message_formatter.py  # Message formatting
└── data/
    └── channel_data.json     # Keep JSON, just make it safer
```

## Key Improvements

### 1. Split into Logical Files (Not Over-Architected)
- **bot.py**: Just the bot setup and event registration
- **commands/**: Group related commands together
- **handlers/**: Reaction and formatting logic
- **context_manager.py**: All the context/state management

### 2. Safer JSON Handling
```python
# context_manager.py
import json
import os
from filelock import FileLock  # pip install filelock

class ContextManager:
    def __init__(self):
        self.contexts = {}
        self.lock = FileLock("data/channel_data.json.lock")
        self.load_all_contexts()
    
    def save_context(self, channel_id):
        """Save with file locking to prevent corruption"""
        with self.lock:
            # Read current data
            data = self._read_json()
            # Update specific channel
            data[str(channel_id)] = self.contexts[channel_id].to_dict()
            # Write atomically
            self._write_json_atomic(data)
    
    def _write_json_atomic(self, data):
        """Write to temp file then rename (atomic on POSIX)"""
        temp_file = "data/channel_data.json.tmp"
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, "data/channel_data.json")
```

### 3. Configuration in One Place
```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Discord
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
COMMAND_PREFIX = "$"

# Defaults
DEFAULT_PARTY_SIZE = 5
MAX_SCHEDULED_HOURS = 4

# Emojis (all in one place!)
EMOJI = {
    "THUMBS_UP": "👍",
    "FULL_STACK": "5️⃣", 
    "REFRESH": "🔄",
    "MENTION": "📣",
    "READY": "✅"
}

# Messages
MESSAGES = {
    "NO_ROLE": "First set the role for the bot to ping with ```$stsr <Role>```",
    "PARTY_FULL": " <:jettpog:724145370023591937>",
    "PARTY_EMPTY": "sadge/{size} <:viper:725612569716326422>"
}
```

### 4. Cleaner Command Organization
```python
# commands/session_commands.py
from discord.ext import commands

class SessionCommands(commands.Cog):
    def __init__(self, bot, context_manager):
        self.bot = bot
        self.contexts = context_manager
    
    @commands.hybrid_command(name="st", description="Starts a Fresh Shooty Session")
    async def start_session(self, ctx):
        # Same logic, just organized
        context = self.contexts.get_context(ctx.channel.id)
        context.backup_state()  # For restore command
        context.reset_users()
        
        message = await ctx.send(context.get_ping_message())
        context.current_message_id = message.id
        await add_reactions(message)
        
        self.contexts.save_context(ctx.channel.id)

# In bot.py, load like this:
async def setup_hook():
    context_manager = ContextManager()
    await bot.add_cog(SessionCommands(bot, context_manager))
```

### 5. Simplified State Management
Keep the same ShootyContext idea, just cleaner:

```python
# context_manager.py
class ShootyContext:
    def __init__(self, channel_id):
        self.channel_id = channel_id
        self.soloq_users = set()
        self.fullstack_users = set()
        self.ready_users = set()
        self.current_message_id = None
        self.role_code = None
        self.game_name = None
        self.party_size = DEFAULT_PARTY_SIZE
        self._backup = None
    
    def backup_state(self):
        """Simple backup for restore command"""
        self._backup = {
            'soloq': self.soloq_users.copy(),
            'fullstack': self.fullstack_users.copy(),
            'ready': self.ready_users.copy()
        }
    
    def restore_state(self):
        """Restore from backup"""
        if self._backup:
            self.soloq_users = self._backup['soloq']
            self.fullstack_users = self._backup['fullstack']
            self.ready_users = self._backup['ready']
    
    def to_dict(self):
        """For JSON serialization"""
        return {
            'role_code': self.role_code,
            'game_name': self.game_name,
            'party_size': self.party_size
        }
    
    @classmethod
    def from_dict(cls, channel_id, data):
        """From JSON deserialization"""
        context = cls(channel_id)
        context.role_code = data.get('role_code')
        context.game_name = data.get('game_name')
        context.party_size = data.get('party_size', DEFAULT_PARTY_SIZE)
        return context
```

## Migration Steps (1-2 days)

### Day 1: Reorganize
1. Create folder structure
2. Move configuration to config.py
3. Split commands into separate files
4. Move reaction handling to its own file

### Day 2: Improve & Test
1. Add file locking for JSON
2. Test all commands still work
3. Add basic logging
4. Update README with new structure

## What We're NOT Doing
- ❌ No database migration (JSON works fine for this scale)
- ❌ No complex dependency injection
- ❌ No abstract repositories or services
- ❌ No extensive testing framework
- ❌ No breaking changes to commands

## Benefits
- ✅ Easier to find and modify specific features
- ✅ Safer data persistence
- ✅ All configuration in one place
- ✅ Can still understand the entire bot quickly
- ✅ Maintains the simple, working approach

## Future Considerations (Only if Needed)
- If bot grows to 50+ servers: Consider SQLite
- If commands exceed 20+: Consider more cogs
- If team grows: Add basic tests
- If performance issues: Add caching

The goal is to make the code more maintainable without losing what makes it good: simplicity and reliability.