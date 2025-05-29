# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ShootyBot is a Discord bot for managing gaming sessions and party formation. It helps users organize groups for multiplayer games by tracking who wants to play, managing party sizes, and facilitating cross-server coordination.

## Architecture

The bot follows a clean, modular architecture:

- **bot.py**: Main entry point that loads cogs and handles Discord events
- **config.py**: All configuration, emojis, and message templates in one place
- **context_manager.py**: State management with atomic JSON file operations and FileLock
- **data_manager.py**: User data and session persistence with comprehensive statistics
- **commands/**: Command cogs organized by functionality (session, party, admin, valorant)
- **handlers/**: Reaction handling and message formatting
- **valorant_client.py**: Henrik API integration for Valorant statistics and account linking
- **match_tracker.py**: Advanced Valorant match analysis and tracking

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (development)
python3 bot.py  # Linux/Mac
py -3 .\bot.py  # Windows

# Run in production (using screen)
./run_python_script.sh

# Run tests
pytest                           # Run all tests
pytest --cov=. --cov-report=html  # Run with coverage report
pytest tests/unit/test_*.py -v    # Run specific test files
```

## Testing

**Comprehensive unit test suite available** (75+ tests):

### Test Commands:
```bash
# Run all tests with coverage
pytest --cov=. --cov-report=html

# Run specific test modules
pytest tests/unit/test_valorant_client.py -v      # API integration tests
pytest tests/unit/commands/test_session_commands.py -v  # Discord command tests
pytest tests/unit/handlers/test_message_formatter.py -v # Message formatting tests

# Test individual components
pytest tests/unit/test_context_manager.py -v     # State management tests
pytest tests/unit/test_data_manager.py -v        # Data persistence tests
```

### Test Coverage:
- **valorant_client.py**: 94% coverage (38 tests) - Henrik API integration
- **commands/session_commands.py**: 96% coverage (19 tests) - Discord commands
- **handlers/message_formatter.py**: 100% coverage (18 tests) - Message formatting
- **context_manager.py**: 92% coverage - State management
- **data_manager.py**: 96% coverage - Data persistence

### Manual Testing:
For features not covered by unit tests:
1. Run the bot locally with a test Discord server
2. Test Discord UI interactions (reactions, slash commands)
3. Verify cross-server webhook functionality
4. Test real-time Valorant API integration

## Key Implementation Details

### Discord Integration:
- **Hybrid commands**: Use Discord.py's hybrid approach (slash + traditional prefix)
- **Cog architecture**: Commands organized in separate cog files with `setup()` functions
- **Reaction handling**: Emojis (👍, 5️⃣, 🔄, 📣) drive user interactions
- **State management**: Per-channel context in `shooty_context_dict`

### Data Management:
- **Atomic operations**: FileLock ensures thread-safe JSON file operations
- **Session tracking**: Comprehensive session statistics and participant history
- **User profiles**: Multi-account Valorant linking with backward compatibility
- **Auto-backup**: State backup/restore functionality for error recovery

### External APIs:
- **Henrik API**: Valorant account info, match history, and statistics
- **Rate limiting**: Proper handling of API rate limits and authentication
- **Real-time data**: Live Valorant activity detection via Discord presence

### Performance:
- **Concurrent operations**: Async/await patterns throughout
- **Efficient state**: Minimal memory footprint with lazy loading
- **Batch operations**: Bulk user operations where possible

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

## Best Practices & Development Guidelines

### Code Organization:
- **Modular design**: Keep related functionality in separate modules
- **Cog pattern**: Use Discord.py cogs for command organization with proper `setup()` functions
- **Config centralization**: All configuration, messages, and emojis in `config.py`
- **Separation of concerns**: Handlers for UI logic, managers for data persistence

### Error Handling:
- **Graceful degradation**: Bot should continue functioning even if external APIs fail
- **User feedback**: Always provide clear error messages to users
- **Logging**: Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- **State recovery**: Implement backup/restore for critical user state

### Testing Strategy:
- **Unit tests first**: Test business logic and API integration thoroughly
- **Mock external dependencies**: Use realistic API response data in tests
- **Discord.py testing**: Test command callbacks directly, not the wrapped commands
- **Coverage targets**: Aim for >90% coverage on core modules

### Performance Considerations:
- **Async patterns**: Use async/await for all I/O operations
- **Rate limiting**: Respect Discord and external API rate limits
- **Memory management**: Clean up unused contexts and data periodically
- **File locking**: Use FileLock for concurrent JSON file access

### Discord Bot Patterns:
- **Hybrid commands**: Support both slash commands and traditional prefix commands
- **Reaction UX**: Use reaction-based interfaces for quick user interactions
- **Context management**: Maintain per-channel state efficiently
- **Permission handling**: Check user permissions before executing admin commands

## Common Gotchas & Troubleshooting

### Discord.py Issues:
- **Command sync timing**: Slash commands may take time to appear in Discord UI
- **Intents**: Ensure proper intents are enabled for message content and reactions
- **Event loop**: Don't mix sync and async code - use proper async patterns
- **Context object**: Always check if context/interaction is still valid before responding

### Data Persistence:
- **FileLock usage**: Always use context managers with FileLock for JSON operations
- **Atomic writes**: Write to temp file first, then rename to prevent corruption
- **Backward compatibility**: Handle old data formats gracefully when adding new fields
- **File permissions**: Ensure bot has read/write access to data directory

### External API Integration:
- **Henrik API changes**: API structure may change - test with real response data
- **Rate limiting**: Implement exponential backoff for rate-limited requests
- **Authentication**: API keys may be required - handle missing keys gracefully
- **Timeouts**: Set reasonable timeouts for API requests to prevent hanging

### Testing Challenges:
- **Discord mocking**: Use proper Mock objects for Discord.py components
- **Async testing**: Use pytest-asyncio and proper async test patterns
- **Time-dependent tests**: Mock datetime.now() for consistent test results
- **File operations**: Use temporary directories for file-based tests

### Production Deployment:
- **Process management**: Use screen/tmux for persistent bot processes
- **Log rotation**: Implement log rotation to prevent disk space issues
- **Environment isolation**: Use virtual environments in production
- **Graceful shutdown**: Handle SIGTERM/SIGINT for clean bot shutdown

### Debugging Tips:
- **Enable debug logging**: Set LOG_LEVEL=DEBUG for detailed operation logs
- **Test with real data**: Use actual Discord servers and API responses for testing
- **State inspection**: Add debug commands to inspect bot state during development
- **Error boundaries**: Catch and log exceptions at appropriate levels

## Development Workflow

### Adding New Features:
1. **Plan the architecture**: Identify which modules need changes
2. **Write tests first**: Create unit tests for new functionality
3. **Implement incrementally**: Add features in small, testable chunks
4. **Test thoroughly**: Run full test suite before committing
5. **Update documentation**: Update CLAUDE.md with new patterns or gotchas

### Code Review Checklist:
- [ ] Unit tests added/updated for new functionality
- [ ] Error handling implemented for failure cases
- [ ] Logging added at appropriate levels
- [ ] Documentation updated (CLAUDE.md, docstrings)
- [ ] Performance impact considered (async patterns, rate limits)
- [ ] Discord.py best practices followed
- [ ] Configuration externalized appropriately

### Release Process:
1. Run full test suite: `pytest --cov=. --cov-report=html`
2. Test manually with real Discord server
3. Update version/changelog if applicable
4. Commit with descriptive commit message
5. Deploy to production with proper process management