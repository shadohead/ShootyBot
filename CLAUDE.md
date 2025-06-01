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

## Advanced Valorant Statistics & API Analysis

### Henrik API Stats Calculation

**Tournament-Grade Accuracy**: ShootyBot implements Henrik API stats calculation that matches tracker.gg with 100% precision for competitive analysis.

#### Verified Stats Implementation:
- ✅ **KAST (Kill/Assist/Survive/Trade)**: Complex multi-factor calculation
- ✅ **First Kills (FK) / First Deaths (FD)**: Timestamp-based chronological analysis  
- ✅ **Multi-Kills (MK)**: Round-based kill count methodology
- ✅ **All basic stats**: K/D/A, damage, economy tracking

#### Key Technical Discoveries:

**KAST Calculation Complexity**:
```python
# KAST requires sophisticated detection beyond basic K/A/S
# - Kill: Any kill in round
# - Assist: Official assists + damage-based assists (50+ damage to killed enemies)
# - Survive: Player alive at round end
# - Trade: Conservative detection (teammate kills your killer within 3 seconds)
```

**Multi-Kill Definition** (Counter-intuitive):
```python
# Tracker.gg uses ROUND-BASED counting, not timing-based
# - Only rounds with 3+ kills count as multi-kills
# - 2-kill rounds do NOT count, regardless of timing
# - This differs from typical FPS multi-kill mechanics
if kills >= 3:
    player_stats[puuid]["multi_kills"] += 1
```

**First Blood Detection**:
```python
# Reliable chronological analysis using kill timestamps
kill_events.sort(key=lambda x: x.get("kill_time_in_round", 0))
first_kill_event = kill_events[0]  # First chronologically
```

### Test-Driven API Reverse Engineering

**Methodology for Achieving 100% Accuracy**:

1. **Create Ground Truth Dataset**:
   ```python
   # Use verified external source (tracker.gg) as test oracle
   expected_stats = {
       "player#tag": {"kast": 68, "fk": 4, "fd": 3, "mk": 1},
       # ... all 10 players from real match
   }
   ```

2. **Comprehensive Test Suite**:
   ```python
   # Zero-tolerance testing for production accuracy
   def test_kast_exact_match(self):
       for player_name, expected in self.expected_stats.items():
           self.assertEqual(calculated_kast, expected["kast"], 
                          f"KAST mismatch for {player_name}")
   ```

3. **Iterative Hypothesis Testing**:
   ```bash
   # Scientific approach to unknown API behavior
   python test_match_stats.py  # Run tests
   # Analyze failures → Form hypothesis → Implement → Repeat
   ```

4. **Data Structure Analysis**:
   ```python
   # Deep dive into Henrik API response structure
   jq '.[:1] | .[0].player_stats[0].kill_events[0] | keys' match_data.json
   # Understand nested data relationships
   ```

### Reverse Engineering Best Practices

**When APIs Don't Match Expected Behavior**:

1. **Hypothesis-Driven Development**:
   - Form specific hypotheses about calculation methods
   - Test each hypothesis systematically with real data
   - Document discoveries for future reference

2. **Ground Truth Validation**:
   - Always use verified external sources as test oracles
   - Never assume your initial understanding is correct
   - Be prepared to discover counter-intuitive behaviors

3. **Comprehensive Edge Case Testing**:
   ```python
   # Test boundary conditions and special cases
   def test_player_with_zero_kills(self):
       # Ensure algorithm handles edge cases correctly
   ```

4. **Data Pattern Analysis**:
   ```python
   # Create analysis tools to understand data patterns
   def analyze_timing_multikills():
       # Custom analysis scripts for hypothesis testing
   ```

### Production API Integration Guidelines

**Rate Limiting & Authentication**:
```python
# Respect Henrik API limits and use authentication properly
headers = {"Authorization": api_key} if api_key else {}
# Implement exponential backoff for rate-limited requests
```

**Error Handling for External APIs**:
```python
try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        return response.json()["data"]
    else:
        # Graceful degradation - don't break bot functionality
        logger.warning(f"Henrik API error: {response.status_code}")
        return None
except requests.RequestException as e:
    logger.error(f"Henrik API request failed: {e}")
    return None
```

**Data Validation & Schema Evolution**:
```python
# Henrik API structure may change - validate before using
kill_events = player_round.get("kill_events", [])
for kill_event in kill_events:
    kill_time = kill_event.get("kill_time_in_round", 0)  # Safe access
```

### Testing External API Integrations

**Mock vs Real Data Balance**:
```python
# Use real API responses for development/testing
def setUpClass(cls):
    # Load real match data for comprehensive testing
    cls.match_data = get_match_data(cls.match_id, cls.api_key)
    
# Mock only for CI/CD where API keys aren't available
@patch('requests.get')
def test_api_failure_handling(self, mock_get):
    mock_get.return_value.status_code = 429  # Rate limited
```

**Data-Driven Test Cases**:
```python
# Use real match data as comprehensive test input
class TestMatchStatsAccuracy(unittest.TestCase):
    # Real match ID with known outcomes
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    
    def test_all_players_all_stats(self):
        # Test every stat for every player - no exceptions
```

### Performance & Scalability

**Concurrent API Operations**:
```python
# Batch API calls when possible
async def get_multiple_matches(match_ids, api_key):
    tasks = [get_match_data(mid, api_key) for mid in match_ids]
    return await asyncio.gather(*tasks)
```

**Caching Strategy**:
```python
# Cache expensive calculations and API responses
@lru_cache(maxsize=100)
def calculate_advanced_stats(match_id):
    # Cache results to avoid recalculation
```

### Key Learnings Summary

1. **Never assume external API behavior matches your expectations**
2. **Test-driven development is essential for API integration accuracy**
3. **Real data beats synthetic test data for complex calculations**
4. **Counter-intuitive behaviors exist in production systems**
5. **Comprehensive test suites catch edge cases that manual testing misses**
6. **Ground truth datasets are invaluable for validating complex algorithms**
7. **Data structure analysis tools accelerate understanding of complex APIs**
8. **Scientific method applies to software development: hypothesis → test → iterate**