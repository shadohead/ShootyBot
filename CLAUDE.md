# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ShootyBot is a Discord bot for managing gaming sessions and party formation. It helps users organize groups for multiplayer games by tracking who wants to play, managing party sizes, and facilitating cross-server coordination.

## Architecture

The bot follows a clean, modular architecture:

- **bot.py**: Main entry point that loads cogs and handles Discord events
- **config.py**: All configuration, emojis, and message templates in one place
- **database.py**: SQLite database layer optimized for Raspberry Pi with ACID compliance
- **context_manager.py**: State management with database persistence
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

# Run in production (using screen with auto-update)
./run_python_script.sh

# CI/CD Auto-Update & Monitoring Commands
./setup_auto_update.sh            # Setup auto-start, monitoring & daily updates
./run_python_script.sh --start         # Start bot manually
./run_python_script.sh --monitor       # Run health check manually
./run_python_script.sh --force-update  # Force immediate update check
./run_python_script.sh --check-only    # Check for updates without applying
tail -f monitor.log                # Monitor health check logs
tail -f update.log                 # Monitor auto-update logs
tail -f cron.log                   # Monitor cron execution logs

# Run tests
pytest                           # Run all tests
pytest --cov=. --cov-report=html  # Run with coverage report
pytest tests/unit/test_*.py -v    # Run specific test files

# Test database system
python3 test_database_fast.py     # Quick database functionality test
python3 migrate_to_sqlite.py --backup  # Migrate from JSON to SQLite with backup
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
- **SQLite database**: ACID-compliant database with WAL mode for better concurrency
- **Raspberry Pi optimized**: Database configuration tuned for Pi's ARM architecture and SD card I/O
- **Session tracking**: Comprehensive session statistics and participant history
- **User profiles**: Multi-account Valorant linking with backward compatibility
- **Auto-migration**: Automatic migration from JSON files to SQLite on first run
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

## MCP (Model Context Protocol) Servers

ShootyBot can leverage MCP servers for enhanced capabilities when working with Claude Code:

### Available MCP Servers:
- **GitHub**: Direct repository management, issue tracking, and pull request creation
- **Web Research**: Real-time web search and content extraction for up-to-date information
- **Context7**: Access to library documentation for frameworks and APIs
- **Perplexity**: Advanced web-based question answering
- **Playwright**: Browser automation for testing Discord web interfaces

### Usage with Claude Code:
When using Claude Code (claude.ai/code) with this project, MCP servers provide:
- **GitHub Integration**: Create issues, manage pull requests, and update code directly
- **Documentation Access**: Fetch latest Discord.py and Henrik API documentation
- **Web Search**: Research gaming APIs, Discord bot patterns, and Valorant data
- **Testing Support**: Automated browser testing for Discord web features

### MCP Configuration:
MCP servers are automatically available in Claude Code. No additional configuration needed in the bot itself.

### Common MCP Use Cases:
1. **API Documentation**: `mcp__Context7__get-library-docs` for Discord.py reference
2. **Issue Creation**: `mcp__github__create_issue` for bug tracking
3. **Web Research**: `mcp__webresearch__search_google` for Valorant API updates
4. **PR Management**: `mcp__github__create_pull_request` for code submissions

## SQLite Database System

ShootyBot uses a lightweight SQLite database optimized for Raspberry Pi 4 deployment:

### Database Features:
- **ACID compliance**: Full transaction support with rollback capability
- **WAL mode**: Write-Ahead Logging for better concurrency and crash recovery
- **Foreign key constraints**: Data integrity enforced at database level
- **Optimized indexes**: Query performance tuned for common access patterns
- **Memory efficient**: 32MB cache size suitable for Raspberry Pi memory constraints

### Database Schema:
- **users**: Discord user profiles with session/game statistics
- **valorant_accounts**: Multiple Valorant accounts per user with primary account support
- **sessions**: Gaming session tracking with participant management
- **session_participants**: Many-to-many relationship for session membership
- **channel_settings**: Per-channel configuration (role codes, game names, party sizes)

### Migration from JSON:
**Automatic Migration**: On first startup, the bot automatically migrates existing JSON data to SQLite:
```bash
# Manual migration with backup (recommended)
python3 migrate_to_sqlite.py --backup

# Force migration even if database exists
python3 migrate_to_sqlite.py --force --backup
```

**Migration Features**:
- Preserves all existing user data and session history
- Handles legacy single-account format → multi-account format conversion
- Creates automatic backup of JSON files
- Validates data integrity after migration
- Shows detailed migration statistics

### Database Management:
```bash
# Test database functionality
python3 test_database_fast.py

# Check database stats (add to bot as admin command)
# Users: 150, Sessions: 1,247, Size: 2.3 MB

# Database optimization (automatic, but can be manual)
# VACUUM and incremental_vacuum for compact storage
```

### Raspberry Pi Optimizations:
- **Reduced I/O**: Batch operations to minimize SD card writes
- **Memory tuning**: Conservative cache sizes for 1-8GB Pi memory configurations
- **Concurrent access**: WAL mode allows simultaneous reads during writes
- **Crash recovery**: Database remains consistent even after power loss
- **Performance**: Sub-second response times for typical bot operations

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
- **Database optimization**: SQLite with WAL mode, indexes, and memory-efficient queries
- **Raspberry Pi tuning**: 32MB cache, MEMORY temp store, and incremental vacuum

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
- **SQLite transactions**: Use ACID transactions for data consistency
- **Database schema**: Normalized schema with foreign key constraints
- **Migration support**: Automatic migration from legacy JSON files
- **Backward compatibility**: Handle old data formats gracefully when adding new fields
- **File permissions**: Ensure bot has read/write access to data directory
- **Database backup**: Regular database optimization with VACUUM command

### External API Integration:
- **Henrik API changes**: API structure may change - test with real response data
- **Rate limiting**: Implement exponential backoff for rate-limited requests
- **Authentication**: API keys may be required - handle missing keys gracefully
- **Timeouts**: Set reasonable timeouts for API requests to prevent hanging

### Testing Challenges:
- **Discord mocking**: Use proper Mock objects for Discord.py components
- **Async testing**: Use pytest-asyncio and proper async test patterns
- **Time-dependent tests**: Mock datetime.now() for consistent test results
- **Database operations**: Use temporary SQLite databases for testing
- **Migration testing**: Test JSON to SQLite migration with sample data
- **Command callback testing**: Test hybrid command callbacks directly using `.callback(cog, ctx)`

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

### Code Quality Issues:
- **Variable scope**: ALWAYS ensure variables are defined before use - trace through execution paths
- **Test before committing**: Write and run tests for any code changes to verify they work
- **Think through edge cases**: Consider scenarios where data might be missing or None
- **Error messages**: Check error logs carefully - undefined variable errors are preventable

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