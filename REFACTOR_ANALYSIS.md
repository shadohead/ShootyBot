# ShootyBot Refactoring Analysis

## Executive Summary

The ShootyBot codebase has grown organically with new features being added over time. While the overall architecture is modular, there are several areas where refactoring would improve code quality, maintainability, and performance. The main issues include code duplication, inconsistent patterns, missing abstractions, and poor separation of concerns.

## Major Issues Identified

### 1. Code Duplication

#### a) JSON File Operations
- **Location**: `context_manager.py` (lines 259-270) and `data_manager.py` (lines 398-409)
- **Issue**: Identical atomic write functionality duplicated across modules
- **Example**:
```python
# Both files have this exact same method:
def _write_json_atomic(self, file_path: str, data: Dict):
    """Write JSON data atomically to prevent corruption"""
    temp_file = f"{file_path}.tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, file_path)
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise e
```

#### b) User Formatting Logic
- **Location**: `context_manager.py` (lines 132-163) and scattered throughout command files
- **Issue**: User list formatting repeated with slight variations
- **Impact**: Changes to formatting require multiple updates

#### c) Error Handling in Commands
- **Location**: All command files (`session_commands.py`, `valorant_commands.py`, etc.)
- **Issue**: Try-except blocks with similar patterns repeated
- **Example**: Slash command handling has duplicate defer/followup logic

### 2. Inconsistent Patterns

#### a) Command Response Handling
- **Issue**: Mixed use of `ctx.send()`, `ctx.reply()`, and slash command specific methods
- **Example from `valorant_commands.py`:
```python
# Lines 48-52: Inconsistent response handling
if hasattr(ctx, 'interaction') and ctx.interaction:
    await ctx.followup.send(embed=embed)
else:
    await ctx.send(embed=embed)
```

#### b) Logging Patterns
- **Issue**: Inconsistent log levels and formats
- Some use `logging.info()`, others `logging.error()`, no consistent format
- Missing logging in critical areas (e.g., session lifecycle)

#### c) Configuration Access
- **Issue**: Direct imports vs. passed parameters
- `config.py` imported with `from config import *` everywhere
- Some functions receive config values as parameters, others access globals

### 3. Missing Abstractions

#### a) No Base Classes for Common Patterns
- All cogs implement similar patterns but no base class
- Session lifecycle management scattered across files
- No abstraction for Discord interaction handling

#### b) Missing Data Access Layer
- Direct dictionary manipulation throughout codebase
- No validation layer for data integrity
- Business logic mixed with data persistence

#### c) No Event System
- Session events (start, end, user join) handled ad-hoc
- No central event bus for cross-component communication

### 4. Poor Separation of Concerns

#### a) Context Manager Responsibilities
- **File**: `context_manager.py`
- **Issues**:
  - Handles both state management AND formatting (lines 115-163)
  - Contains Discord-specific logic (bold_readied_user)
  - Mixes data persistence with business logic

#### b) Valorant Client Overreach
- **File**: `valorant_client.py`
- **Issues**:
  - Contains Discord presence checking (lines 134-157)
  - Manages data persistence directly (lines 99-101)
  - Complex statistics calculations mixed with API calls

#### c) Match Tracker Complexity
- **File**: `match_tracker.py`
- **Issues**:
  - Handles tracking, formatting, AND Discord posting
  - Embed creation logic embedded in tracker (lines 206-304)
  - Configuration constants hardcoded (lines 13-19)

### 5. Complex Functions

#### a) Statistics Calculation
- **Location**: `valorant_client.py`, `calculate_player_stats()` (lines 178-339)
- **Issue**: 160+ line function doing multiple things
- Should be split into: data extraction, calculation, aggregation

#### b) Match Tracking Logic
- **Location**: `match_tracker.py`, `_check_recent_matches()` (lines 91-155)
- **Issue**: Nested loops and complex conditionals
- Difficult to test individual components

#### c) Message Formatting
- **Location**: `handlers/message_formatter.py`, `party_status_message()`
- **Issue**: Complex conditional logic for status generation
- Parameter handling is confusing (backward compatibility hack)

### 6. Missing Type Hints

Most functions lack type hints, making it difficult to understand:
- Expected parameter types
- Return value types
- Optional vs. required parameters

**Examples**:
```python
# Current:
def get_ping_shooty_message(role_code):
def party_status_message(is_ping, user_sets):

# Should be:
def get_ping_shooty_message(role_code: Optional[str]) -> str:
def party_status_message(is_ping: Union[bool, discord.TextChannel], user_sets: ShootyContext) -> str:
```

### 7. Configuration Issues

#### a) Mixed Configuration Sources
- Environment variables, .env file, and legacy DiscordConfig.py
- No validation of required vs. optional config
- Magic strings and numbers throughout code

#### b) Hardcoded Values
- **Examples**:
  - `match_tracker.py`: CHECK_INTERVAL_SECONDS = 300
  - `config.py`: MAX_SCHEDULED_HOURS = 4
  - Emoji codes scattered in config and code

### 8. Error Handling Inconsistencies

#### a) Silent Failures
- Many try-except blocks catch all exceptions and only log
- No user feedback for certain failures
- Lost stack traces in some error handlers

#### b) API Error Handling
- `valorant_client.py`: Different error handling for each endpoint
- No retry logic for transient failures
- Rate limiting not properly handled

## Prioritized Refactoring Opportunities

### Priority 1: Core Infrastructure (High Impact, Foundation for other changes)

1. **Create Common Base Classes**
   - `BaseCommand`: Handle common command patterns, error handling
   - `BaseDataManager`: Abstract file operations, validation
   - `BaseAPIClient`: Common HTTP handling, retries, rate limiting

2. **Extract Shared Utilities**
   - Create `utils/file_operations.py` for atomic writes
   - Create `utils/formatting.py` for all Discord formatting
   - Create `utils/discord_helpers.py` for interaction handling

3. **Implement Proper Data Access Layer**
   - Create data models with validation
   - Separate business logic from persistence
   - Add data migration support

### Priority 2: Code Organization (Medium Impact, Improves maintainability)

1. **Refactor Large Functions**
   - Split `calculate_player_stats()` into smaller functions
   - Extract embed creation from match tracker
   - Simplify message formatting logic

2. **Consistent Error Handling**
   - Create error handler decorators
   - Implement proper error types
   - Add user-friendly error messages

3. **Add Type Hints Throughout**
   - Start with public APIs
   - Add to data models
   - Use typing module features (Optional, Union, etc.)

### Priority 3: Feature Improvements (Lower Impact, Quality of life)

1. **Configuration Management**
   - Create configuration schema with validation
   - Centralize all config in one place
   - Remove magic strings/numbers

2. **Event System Implementation**
   - Create event bus for session lifecycle
   - Decouple components through events
   - Enable plugin architecture

3. **Improve Logging**
   - Implement structured logging
   - Add request IDs for tracing
   - Create log levels policy

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- Extract common utilities
- Create base classes
- Add comprehensive type hints

### Phase 2: Data Layer (Week 3-4)
- Implement data models
- Create data access layer
- Add validation and migrations

### Phase 3: Component Refactoring (Week 5-6)
- Refactor large functions
- Implement consistent patterns
- Fix separation of concerns

### Phase 4: Polish (Week 7-8)
- Improve error handling
- Add missing tests
- Update documentation

## Code Metrics

### Current State:
- **Total Lines**: ~3,500
- **Duplicate Code**: ~15% (estimated)
- **Functions > 50 lines**: 8
- **Type Hint Coverage**: <10%
- **Test Coverage**: 75%+ (good!)

### Target State:
- **Duplicate Code**: <5%
- **Functions > 50 lines**: 0
- **Type Hint Coverage**: >90%
- **Test Coverage**: >85%

## Conclusion

The ShootyBot codebase is functional but would benefit significantly from refactoring. The main priorities should be:

1. **Eliminating code duplication** through shared utilities
2. **Implementing consistent patterns** with base classes
3. **Improving separation of concerns** with proper layers
4. **Adding type hints** for better code clarity

The existing test suite (75%+ coverage) provides a good safety net for refactoring. The modular architecture (cogs) is a strength that should be preserved and enhanced.