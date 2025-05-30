#!/bin/bash

# CI/CD-like script for ShootyBot with automatic updates
# Checks for GitHub updates daily at 5 AM and restarts if needed

# Configuration
SCREEN_NAME="shooty"
LOG_FILE="update.log"
UPDATE_CHECK_HOUR=5  # 5 AM
LAST_CHECK_FILE=".last_update_check"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
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

# Function to start the bot
start_bot() {
    log "🚀 Starting bot..."
    screen -dmS ${SCREEN_NAME} ./run.sh
    sleep 2
    
    if screen -list | grep -q "${SCREEN_NAME}"; then
        log "✅ Bot started successfully"
    else
        log "❌ Failed to start bot"
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

# Daily update check logic
if should_check_updates; then
    log "⏰ Daily update check triggered"
    if check_for_updates; then
        apply_updates
    fi
    mark_check_done
fi

# Check if the screen session is already running
if ! screen -list | grep -q "${SCREEN_NAME}"; then
    log "🔄 Bot not running, starting..."
    start_bot
else
    log "✅ Bot is already running"
fi