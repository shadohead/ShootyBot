#!/bin/bash

# Setup script for ShootyBot auto-update cron job
# This creates a cron job that runs every hour to check for updates

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_CRON_JOB="*/5 * * * * cd ${SCRIPT_DIR} && ./run_python_script.sh --monitor >> cron.log 2>&1"
STARTUP_CRON_JOB="@reboot cd ${SCRIPT_DIR} && ./run_python_script.sh --start >> cron.log 2>&1"

echo "🔧 Setting up ShootyBot auto-update cron job..."
echo "📂 Script directory: ${SCRIPT_DIR}"

# Check if cron jobs already exist
if crontab -l 2>/dev/null | grep -q "run_python_script.sh"; then
    echo "⚠️ Cron jobs already exist. Removing old ones..."
    crontab -l 2>/dev/null | grep -v "run_python_script.sh" | crontab -
fi

# Add new cron jobs
echo "➕ Adding cron jobs for monitoring and auto-start..."
(crontab -l 2>/dev/null; echo "$MONITOR_CRON_JOB") | crontab -
(crontab -l 2>/dev/null; echo "$STARTUP_CRON_JOB") | crontab -

# Verify cron jobs were added
if crontab -l 2>/dev/null | grep -q "run_python_script.sh"; then
    echo "✅ Cron jobs successfully added!"
    echo ""
    echo "📋 Current cron jobs:"
    crontab -l | grep "run_python_script.sh"
    echo ""
    echo "ℹ️ The bot will now:"
    echo "   • Auto-start on system reboot"
    echo "   • Health check every 5 minutes"
    echo "   • Auto-restart if bot goes down"
    echo "   • Check for updates daily at 5 AM"
    echo "   • Restart automatically if updates are found"
    echo "   • Log all activities to update.log, monitor.log and cron.log"
    echo ""
    echo "🛠️ Manual commands:"
    echo "   ./run_python_script.sh --start         # Start bot manually"
    echo "   ./run_python_script.sh --monitor       # Run health check"
    echo "   ./run_python_script.sh --force-update  # Force update check"
    echo "   ./run_python_script.sh --check-only    # Check without applying"
    echo "   tail -f monitor.log                    # Monitor health logs"
    echo "   tail -f update.log                     # Monitor update logs"
    echo "   tail -f cron.log                       # Monitor cron logs"
else
    echo "❌ Failed to add cron job"
    exit 1
fi