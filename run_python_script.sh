#!/bin/bash

# CI/CD-like script for ShootyBot with automatic updates
# Checks for GitHub updates daily at 5 AM and restarts if needed

# Configuration
SCREEN_NAME="shooty"
LOG_FILE="update.log"
MONITOR_LOG_FILE="monitor.log"
UPDATE_CHECK_HOUR=5  # 5 AM (only used by the legacy daily fallback path)
LAST_CHECK_FILE=".last_update_check"
HEALTH_CHECK_FILE=".bot_health"
# Marker written by the bot (bot.py) holding "<active_session_count> <epoch>".
# Used to defer an update-restart while a session is in progress.
ACTIVE_SESSION_FILE=".active_session"
# Treat the marker as authoritative only if updated within this many seconds;
# a stale marker means the bot is down, so there is no session to protect.
ACTIVE_SESSION_FRESH_SECS=600
# systemd unit installed by setup_systemd.sh. When present we restart through
# systemd instead of the legacy screen session.
SYSTEMD_SERVICE="shootybot.service"

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

# Returns 0 if a session is currently in progress (so we should NOT restart),
# 1 otherwise. Reads the marker the bot writes; a missing or stale marker means
# the bot isn't reporting an active session, so updating is safe.
bot_has_active_session() {
    [ -f "${ACTIVE_SESSION_FILE}" ] || return 1

    local content count ts now age
    content=$(cat "${ACTIVE_SESSION_FILE}" 2>/dev/null)
    count=$(echo "${content}" | awk '{print $1}')
    ts=$(echo "${content}" | awk '{print $2}')

    # Bail out (treat as no session) on malformed content
    [[ "${count}" =~ ^[0-9]+$ ]] || return 1
    [[ "${ts}" =~ ^[0-9]+$ ]] || return 1

    now=$(date +%s)
    age=$((now - ts))
    # Stale marker -> bot is likely down -> nothing to protect
    if [ "${age}" -gt "${ACTIVE_SESSION_FRESH_SECS}" ]; then
        return 1
    fi

    [ "${count}" -gt 0 ]
}

# True when the bot is managed by the systemd service (production path):
# systemd is available AND our service unit is actually installed. Checking the
# unit file directly avoids false positives on screen/cron hosts that happen to
# run systemd but never installed our service.
under_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -f "/etc/systemd/system/${SYSTEMD_SERVICE}" ]
}

# Reinstall the systemd units from the (freshly pulled) deploy/ directory so a
# change to the timer cadence or service definition actually takes effect. This
# is what lets THIS change (5 AM -> every 15 min) auto-deploy on the next pull.
# Needs root: attempted non-interactively (sudo -n); if unavailable we log the
# one command an operator must run once.
reinstall_systemd_units() {
    local bot_user
    bot_user=$(stat -c %U "${SCRIPT_DIR}" 2>/dev/null || echo "${USER}")

    log "🧩 Reinstalling systemd units (deploy files changed)..."
    if [ "$(id -u)" -eq 0 ]; then
        ./setup_systemd.sh "${bot_user}" >>"${LOG_FILE}" 2>&1 && return 0
    elif sudo -n true 2>/dev/null; then
        sudo -n ./setup_systemd.sh "${bot_user}" >>"${LOG_FILE}" 2>&1 && return 0
    fi

    log "⚠️ Could not reinstall systemd units automatically (need root)."
    log "   Run once to activate the new update schedule: sudo ./setup_systemd.sh ${bot_user}"
    return 1
}

# Self-heal: if the installed update timer no longer matches the one in the
# repo (e.g. this very change bumped it from daily 5 AM to every 15 min),
# reinstall the units so the new schedule takes effect — even when there's no
# new commit to pull. This is what makes the cadence change converge on its own
# after the (older) updater first pulls it. Reinstalling units does NOT restart
# the bot, so it's safe to run during a session.
ensure_systemd_units_current() {
    under_systemd || return 0

    local repo_timer="deploy/shootybot-update.timer"
    local installed_timer="/etc/systemd/system/shootybot-update.timer"
    [ -f "${repo_timer}" ] || return 0

    if [ ! -f "${installed_timer}" ] || ! cmp -s "${repo_timer}" "${installed_timer}"; then
        log "🧩 Installed update timer differs from repo — reinstalling units"
        reinstall_systemd_units
    fi
}

# Restart the bot, preferring systemd; fall back to signaling the process
# (systemd's Restart= policy relaunches it) and finally to the screen path.
restart_bot() {
    if under_systemd; then
        log "🔁 Restarting via systemd (${SYSTEMD_SERVICE})..."
        if [ "$(id -u)" -eq 0 ] && systemctl restart "${SYSTEMD_SERVICE}" 2>>"${LOG_FILE}"; then
            return 0
        elif sudo -n systemctl restart "${SYSTEMD_SERVICE}" 2>>"${LOG_FILE}"; then
            return 0
        fi
        # No privileges for systemctl: signal the bot and let systemd relaunch
        # it (the update runs in its own cgroup, so this doesn't kill us).
        log "⚠️ No sudo for systemctl; signaling bot, systemd will relaunch it."
        pkill -f "python.*bot.py" 2>/dev/null
        return 0
    fi

    # Legacy (dev / screen) path
    start_bot
}

# Function to apply updates and restart bot
apply_updates() {
    # Don't interrupt players: if a session is in progress, defer this update.
    # We intentionally do NOT pull, so the next cycle re-detects the update and
    # tries again once the session has ended.
    if bot_has_active_session; then
        log "⏸️ Session in progress — deferring update (will retry next cycle)"
        return 0
    fi

    log "🔄 Applying updates..."

    # Remember where we were so we can tell what the pull changed.
    local pre_pull_hash
    pre_pull_hash=$(git rev-parse HEAD)

    # Pull latest changes
    git pull origin main 2>&1 | tee -a "${LOG_FILE}"

    if [ $? -eq 0 ]; then
        log "✅ Updates applied successfully"

        local changed
        changed=$(git diff --name-only "${pre_pull_hash}" HEAD 2>/dev/null)

        # Update dependencies if requirements.txt changed
        if echo "${changed}" | grep -q "requirements.txt"; then
            log "📦 Updating dependencies..."
            source venv/bin/activate && pip install -r requirements.txt 2>&1 | tee -a "${LOG_FILE}"
        fi

        # Self-deploy: if the systemd unit definitions changed, reinstall them
        # so the new schedule/service takes effect.
        if echo "${changed}" | grep -qE '^(deploy/|setup_systemd\.sh)'; then
            reinstall_systemd_units
        fi

        # Restart the bot to run the new code
        restart_bot
    else
        log "❌ Failed to apply updates"
        # Try to restart with current version
        restart_bot
    fi
}

# Function to check if bot is healthy
is_bot_healthy() {
    # Verify a python process is running for the bot
    if ! pgrep -f "python.*bot.py" >/dev/null; then
        return 1  # Bot process not found
    fi

    # If health file exists, ensure it's been updated recently
    if [ -f "$HEALTH_CHECK_FILE" ]; then
        local last_health=$(stat -c %Y "$HEALTH_CHECK_FILE" 2>/dev/null || echo "0")
        local current_time=$(date +%s)
        if [[ "$last_health" =~ ^[0-9]+$ ]]; then
            local time_diff=$((current_time - last_health))
            # Allow up to 15 minutes before considering the bot unhealthy
            if [ $time_diff -gt 900 ]; then
                monitor_log "Health check file stale ($time_diff s)"
                return 1
            fi
        fi
    else
        monitor_log "Health check file missing but process running"
    fi

    return 0
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
    
    # Update dependencies before starting
    monitor_log "📦 Updating dependencies..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate && pip install -r requirements.txt --quiet --upgrade
        if [ $? -eq 0 ]; then
            monitor_log "✅ Dependencies updated"
        else
            monitor_log "⚠️ Failed to update some dependencies, continuing anyway..."
        fi
    fi
    
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
        monitor_log "✅ Bot is healthy"
        # Don't touch the health file - let the bot manage it
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
    # Converge the systemd schedule first (no-op once units match the repo).
    ensure_systemd_units_current
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
