#!/bin/bash

# Setup script for ShootyBot auto-update cron job
# This creates a cron job that runs every hour to check for updates

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_JOB="0 * * * * cd ${SCRIPT_DIR} && ./run_python_script.sh >> cron.log 2>&1"

echo "🔧 Setting up ShootyBot auto-update cron job..."
echo "📂 Script directory: ${SCRIPT_DIR}"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "run_python_script.sh"; then
    echo "⚠️ Cron job already exists. Removing old one..."
    crontab -l 2>/dev/null | grep -v "run_python_script.sh" | crontab -
fi

# Add new cron job
echo "➕ Adding cron job to run every hour..."
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

# Verify cron job was added
if crontab -l 2>/dev/null | grep -q "run_python_script.sh"; then
    echo "✅ Cron job successfully added!"
    echo ""
    echo "📋 Current cron jobs:"
    crontab -l | grep "run_python_script.sh"
    echo ""
    echo "ℹ️ The bot will now:"
    echo "   • Check for updates daily at 5 AM"
    echo "   • Restart automatically if updates are found"
    echo "   • Keep running if no updates are available"
    echo "   • Log all activities to update.log and cron.log"
    echo ""
    echo "🛠️ Manual commands:"
    echo "   ./run_python_script.sh --force-update  # Force update check"
    echo "   ./run_python_script.sh --check-only    # Check without applying"
    echo "   tail -f update.log                     # Monitor update logs"
    echo "   tail -f cron.log                       # Monitor cron logs"
else
    echo "❌ Failed to add cron job"
    exit 1
fi