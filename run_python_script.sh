#!/bin/bash

# CI/CD-like script for ShootyBot with automatic updates
# Checks for GitHub updates daily at 5 AM and restarts if needed

# Configuration
SCREEN_NAME="shooty"
LOG_FILE="update.log"
MONITOR_LOG_FILE="monitor.log"
UPDATE_CHECK_HOUR=5  # 5 AM
LAST_CHECK_FILE=".last_update_check"
HEALTH_CHECK_FILE=".bot_health"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

monitor_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${MONITOR_LOG_FILE}"
}

# Function to check for updates
check_for_updates() {
    log "🔍 Checking for GitHub updates..."
    
    # Fetch latest changes from remote
    git fetch origin main 2>&1 | tee -a "${LOG_FILE}"
    
    # Check if there are new commits
    LOCAL_HASH=$(git rev-parse HEAD)
    REMOTE_HASH=$(git rev-parse origin/main)
    
    if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
        log "📦 Updates found! Local: $LOCAL_HASH, Remote: $REMOTE_HASH"
        return 0  # Updates available
    else
        log "✅ No updates available"
        return 1  # No updates
    fi
}

# Function to apply updates and restart bot
apply_updates() {
    log "🔄 Applying updates..."
    
    # Stop the bot if running
    if screen -list | grep -q "${SCREEN_NAME}"; then
        log "🛑 Stopping bot..."
        screen -S "${SCREEN_NAME}" -X quit
        sleep 3
    fi
    
    # Pull latest changes
    git pull origin main 2>&1 | tee -a "${LOG_FILE}"
    
    if [ $? -eq 0 ]; then
        log "✅ Updates applied successfully"
        
        # Update dependencies if requirements.txt changed
        if git diff HEAD~1 HEAD --name-only | grep -q "requirements.txt"; then
            log "📦 Updating dependencies..."
            source venv/bin/activate && pip install -r requirements.txt 2>&1 | tee -a "${LOG_FILE}"
        fi
        
        # Restart the bot
        start_bot
    else
        log "❌ Failed to apply updates"
        # Try to restart with current version
        start_bot
    fi
}

# Function to check if bot is healthy
is_bot_healthy() {
    # Check if screen session exists
    if ! screen -list | grep -q "${SCREEN_NAME}"; then
        return 1  # Bot not running
    fi
    
    # Check if health file is recent (updated within last 5 minutes)
    if [ -f "$HEALTH_CHECK_FILE" ]; then
        local last_health=$(stat -f %m "$HEALTH_CHECK_FILE" 2>/dev/null || stat -c %Y "$HEALTH_CHECK_FILE" 2>/dev/null || echo "0")
        local current_time=$(date +%s)
        if [[ "$last_health" =~ ^[0-9]+$ ]]; then
            local time_diff=$((current_time - last_health))
        else
            return 1  # Invalid timestamp
        fi
        
        if [ $time_diff -gt 300 ]; then  # 5 minutes
            return 1  # Health check is stale
        fi
    else
        return 1  # No health file
    fi
    
    return 0  # Bot is healthy
}

# Function to start the bot
start_bot() {
    monitor_log "🚀 Starting bot..."
    
    # Kill any existing screen session first
    if screen -list | grep -q "${SCREEN_NAME}"; then
        monitor_log "🛑 Stopping existing bot instance..."
        screen -S "${SCREEN_NAME}" -X quit
        sleep 3
    fi
    
    # Kill any lingering Python bot processes
    pkill -f "python.*bot.py" 2>/dev/null
    sleep 2
    
    # Start new instance
    screen -dmS ${SCREEN_NAME} ./run.sh
    sleep 3
    
    if screen -list | grep -q "${SCREEN_NAME}"; then
        monitor_log "✅ Bot started successfully"
        # Update health file
        touch "$HEALTH_CHECK_FILE"
    else
        monitor_log "❌ Failed to start bot"
        return 1
    fi
}

# Function to monitor bot health and restart if needed
monitor_bot() {
    if ! is_bot_healthy; then
        monitor_log "⚠️ Bot health check failed - restarting..."
        start_bot
        
        # Wait and check again
        sleep 5
        if is_bot_healthy; then
            monitor_log "✅ Bot successfully restarted"
        else
            monitor_log "❌ Bot restart failed - will retry next check"
        fi
    else
        # Update health file to show monitoring is active
        touch "$HEALTH_CHECK_FILE"
    fi
}

# Function to check if it's time for daily update check
should_check_updates() {
    current_hour=$(date +%H)
    current_date=$(date +%Y-%m-%d)
    
    # Check if it's the right hour
    if [ "$current_hour" -eq "$UPDATE_CHECK_HOUR" ]; then
        # Check if we haven't already checked today
        if [ -f "$LAST_CHECK_FILE" ]; then
            last_check_date=$(cat "$LAST_CHECK_FILE")
            if [ "$last_check_date" = "$current_date" ]; then
                return 1  # Already checked today
            fi
        fi
        return 0  # Time to check
    fi
    return 1  # Not time yet
}

# Function to mark update check as done for today
mark_check_done() {
    date +%Y-%m-%d > "$LAST_CHECK_FILE"
}

# Main logic

# If --monitor is passed, run health monitoring
if [ "$1" = "--monitor" ]; then
    monitor_log "🔍 Health check monitoring"
    monitor_bot
    exit 0
fi

# If --force-update is passed, force an update check
if [ "$1" = "--force-update" ]; then
    log "🔧 Force update requested"
    if check_for_updates; then
        apply_updates
    else
        log "ℹ️ No updates to apply"
    fi
    mark_check_done
    exit 0
fi

# If --check-only is passed, just check for updates without applying
if [ "$1" = "--check-only" ]; then
    check_for_updates
    exit $?
fi

# If --start is passed, just start the bot
if [ "$1" = "--start" ]; then
    start_bot
    exit 0
fi

# Daily update check logic
if should_check_updates; then
    log "⏰ Daily update check triggered"
    if check_for_updates; then
        apply_updates
    fi
    mark_check_done
fi

# Always run health monitoring to ensure bot is running
monitor_bot