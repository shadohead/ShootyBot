# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ShootyBot is a Discord bot for managing gaming sessions and party formation. It helps users organize groups for multiplayer games by tracking who wants to play, managing party sizes, and facilitating cross-server coordination.

## Architecture

The bot now follows a clean, modular architecture:

- **bot.py**: Main entry point that loads cogs and handles Discord events
- **config.py**: All configuration, emojis, and message templates in one place
- **context_manager.py**: State management with atomic JSON file operations
- **commands/**: Command cogs organized by functionality (session, party, admin)
- **handlers/**: Reaction handling and message formatting

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (development)
python3 bot.py  # Linux/Mac
py -3 .\bot.py  # Windows

# Run in production (using screen)
./run_python_script.sh
```

## Testing

No formal test suite exists. Test manually by:
1. Running the bot locally with a test Discord server
2. Testing each command and reaction handler
3. Verifying state persistence across restarts

## Key Implementation Details

- Commands use Discord.py's hybrid command approach (slash + traditional prefix)
- User state is managed per-channel in `shooty_context_dict`
- Settings persist to `channel_data.json` on changes
- Reactions (👍, 5️⃣, 🔄, 📣) drive user interactions
- Cross-server LFG uses webhook integrations

## Configuration

**Option 1 (Recommended)**: Create a `.env` file (copy from `.env.example`):
```
BOT_TOKEN=your_discord_bot_token
SHOOTY_ROLE_CODE=<@&your_role_id>
HENRIK_API_KEY=your_henrik_key_here  # Optional - for higher rate limits
LOG_LEVEL=INFO
```

**Option 2**: Set environment variables directly
**Option 3**: Use the legacy `DiscordConfig.py` file (copy from `example.DiscordConfig.py`)

The bot will check for configuration in this order: `.env` file → environment variables → `DiscordConfig.py`