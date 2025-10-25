# Auto-Update System Improvements

This document outlines potential improvements to ShootyBot's auto-update system, organized by priority and category.

## 🚨 Critical Improvements (High Priority)

### 1. Automatic Rollback on Failed Updates

**Problem:** If an update breaks the bot, it stays broken until manual intervention.

**Solution:** Implement automatic rollback on failure

```bash
# In run_python_script.sh - Enhanced apply_updates()
apply_updates() {
    log "🔄 Applying updates..."

    # Save current commit hash before updating
    PREVIOUS_COMMIT=$(git rev-parse HEAD)
    log "Current version: $PREVIOUS_COMMIT"

    # Create automatic backup of database
    if [ -f "shooty_bot.db" ]; then
        cp shooty_bot.db "shooty_bot.db.backup.$(date +%Y%m%d_%H%M%S)"
        log "📦 Database backup created"
    fi

    # Stop the bot
    stop_bot

    # Pull updates
    git pull origin main 2>&1 | tee -a "${LOG_FILE}"

    if [ $? -eq 0 ]; then
        log "✅ Git pull successful"
        NEW_COMMIT=$(git rev-parse HEAD)

        # Update dependencies if needed
        if git diff $PREVIOUS_COMMIT $NEW_COMMIT --name-only | grep -q "requirements.txt"; then
            log "📦 Updating dependencies..."
            source venv/bin/activate && pip install -r requirements.txt 2>&1 | tee -a "${LOG_FILE}"
        fi

        # Start bot and verify it's healthy
        start_bot
        sleep 10

        # Smoke test: Check if bot started successfully
        if is_bot_healthy; then
            log "✅ Update successful - bot is healthy"
            # Clean up old backups (keep last 5)
            ls -t shooty_bot.db.backup.* 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null
        else
            log "❌ Bot unhealthy after update - ROLLING BACK"
            rollback_update "$PREVIOUS_COMMIT"
        fi
    else
        log "❌ Git pull failed"
        start_bot  # Try to restart with current version
    fi
}

rollback_update() {
    local rollback_commit=$1
    log "🔄 Rolling back to $rollback_commit"

    # Hard reset to previous commit
    git reset --hard "$rollback_commit" 2>&1 | tee -a "${LOG_FILE}"

    # Restore dependencies to previous state
    source venv/bin/activate && pip install -r requirements.txt 2>&1 | tee -a "${LOG_FILE}"

    # Restore database backup if exists
    latest_backup=$(ls -t shooty_bot.db.backup.* 2>/dev/null | head -1)
    if [ -n "$latest_backup" ]; then
        cp "$latest_backup" shooty_bot.db
        log "📦 Database restored from backup"
    fi

    # Restart bot
    start_bot

    # Send alert (Discord webhook, email, etc.)
    send_alert "⚠️ ShootyBot auto-update FAILED and rolled back to $rollback_commit"
}
```

**Benefits:**
- Zero manual intervention needed for failed updates
- Automatic database backup and restore
- Bot stays functional even when updates fail

---

### 2. Discord Notifications for Updates

**Problem:** No visibility into update status unless you check logs.

**Solution:** Send Discord notifications via webhook

```python
# Add to bot or create separate notification script
import requests
import os

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_ADMIN_WEBHOOK_URL')

def send_discord_notification(title, description, color, fields=None):
    """Send rich embed notification to Discord admin channel"""
    if not DISCORD_WEBHOOK_URL:
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,  # Green: 0x00ff00, Red: 0xff0000, Yellow: 0xffaa00
        "timestamp": datetime.utcnow().isoformat(),
        "fields": fields or []
    }

    requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})

# Usage in update script:
send_discord_notification(
    title="🔄 ShootyBot Update Started",
    description=f"Updating from {old_commit[:7]} to {new_commit[:7]}",
    color=0xffaa00,
    fields=[
        {"name": "Commits", "value": str(commit_count), "inline": True},
        {"name": "Time", "value": datetime.now().strftime("%Y-%m-%d %H:%M"), "inline": True}
    ]
)
```

**Bash integration:**
```bash
# Add to run_python_script.sh
send_discord_alert() {
    local message=$1
    local color=${2:-16776960}  # Default: yellow

    if [ -n "$DISCORD_ADMIN_WEBHOOK_URL" ]; then
        curl -H "Content-Type: application/json" \
             -d "{\"embeds\": [{\"description\": \"$message\", \"color\": $color}]}" \
             "$DISCORD_ADMIN_WEBHOOK_URL" 2>/dev/null
    fi
}

# Usage:
send_discord_alert "✅ ShootyBot updated successfully to $(git rev-parse --short HEAD)" 65280  # Green
send_discord_alert "❌ ShootyBot update failed - rolled back" 16711680  # Red
```

**Benefits:**
- Instant notification of update status
- No need to SSH and check logs
- Can ping specific admins on failures

---

### 3. Graceful Shutdown

**Problem:** Bot shuts down immediately, potentially interrupting active gaming sessions.

**Solution:** Implement graceful shutdown with session awareness

```python
# Add to bot.py
import signal
import asyncio

class ShootyBot(commands.Bot):
    def __init__(self):
        super().__init__(...)
        self.shutting_down = False
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully"""
        if not self.shutting_down:
            self.shutting_down = True
            asyncio.create_task(self.graceful_shutdown())

    async def graceful_shutdown(self):
        """Gracefully shutdown bot, finishing active sessions"""
        logging.info("🛑 Graceful shutdown initiated...")

        # Check for active sessions
        active_sessions = []
        for channel_id, context in shooty_context_dict.items():
            if context.get('session_active'):
                active_sessions.append(channel_id)

        if active_sessions:
            logging.info(f"⏳ Waiting for {len(active_sessions)} active sessions to complete...")

            # Send warning to active sessions
            for channel_id in active_sessions:
                try:
                    channel = self.get_channel(channel_id)
                    await channel.send("⚠️ Bot is updating soon. Please finish your session within 5 minutes.")
                except:
                    pass

            # Wait max 5 minutes for sessions to end
            for i in range(30):  # 30 * 10s = 5 minutes
                await asyncio.sleep(10)
                active = sum(1 for cid in active_sessions
                           if shooty_context_dict.get(cid, {}).get('session_active'))
                if active == 0:
                    break
                logging.info(f"⏳ {active} sessions still active...")

        logging.info("✅ Shutting down cleanly")
        await self.close()
```

**Update script integration:**
```bash
# In run_python_script.sh - Enhanced stop_bot()
stop_bot() {
    if screen -list | grep -q "${SCREEN_NAME}"; then
        log "🛑 Requesting graceful shutdown..."

        # Send SIGTERM for graceful shutdown (not SIGKILL)
        bot_pid=$(pgrep -f "python.*bot.py")
        if [ -n "$bot_pid" ]; then
            kill -TERM $bot_pid

            # Wait up to 5 minutes for graceful shutdown
            for i in {1..60}; do
                if ! pgrep -f "python.*bot.py" >/dev/null; then
                    log "✅ Bot shut down gracefully"
                    return 0
                fi
                sleep 5
            done

            # Force kill if still running
            log "⚠️ Graceful shutdown timeout - forcing kill"
            pkill -9 -f "python.*bot.py"
        fi

        screen -S "${SCREEN_NAME}" -X quit
        sleep 3
    fi
}
```

**Benefits:**
- Doesn't interrupt active gaming sessions
- Users get warning before bot goes down
- Professional user experience

---

## ⚠️ Important Improvements (Medium Priority)

### 4. Pre-Deployment Testing

**Problem:** Updates go straight to production without validation.

**Solution:** Add smoke tests before marking update as successful

```python
# smoke_tests.py - Run quick validation tests after update
import asyncio
import sys
import os
from bot import ShootyBot

async def run_smoke_tests():
    """Quick validation tests to ensure bot is functional"""
    tests_passed = 0
    tests_failed = 0

    try:
        # Test 1: Bot can initialize
        print("🧪 Test 1: Bot initialization...")
        bot = ShootyBot()
        print("✅ Bot initialized")
        tests_passed += 1

        # Test 2: Database connection
        print("🧪 Test 2: Database connection...")
        from database import get_db
        db = get_db()
        db.cursor().execute("SELECT COUNT(*) FROM users")
        print("✅ Database accessible")
        tests_passed += 1

        # Test 3: Config loaded
        print("🧪 Test 3: Configuration...")
        from config import BOT_TOKEN
        assert BOT_TOKEN is not None
        print("✅ Configuration loaded")
        tests_passed += 1

        # Test 4: Commands loaded
        print("🧪 Test 4: Commands loading...")
        # Import commands to ensure no syntax errors
        from commands import session_commands, valorant_commands
        print("✅ Commands loaded")
        tests_passed += 1

        print(f"\n✅ Smoke tests passed: {tests_passed}/{tests_passed + tests_failed}")
        return True

    except Exception as e:
        tests_failed += 1
        print(f"\n❌ Smoke tests failed: {e}")
        print(f"Results: {tests_passed} passed, {tests_failed} failed")
        return False

if __name__ == "__main__":
    result = asyncio.run(run_smoke_tests())
    sys.exit(0 if result else 1)
```

**Integration in update script:**
```bash
# In apply_updates() after git pull
log "🧪 Running smoke tests..."
source venv/bin/activate && python3 smoke_tests.py 2>&1 | tee -a "${LOG_FILE}"

if [ $? -eq 0 ]; then
    log "✅ Smoke tests passed - deploying update"
    start_bot
else
    log "❌ Smoke tests failed - rolling back"
    rollback_update "$PREVIOUS_COMMIT"
fi
```

**Benefits:**
- Catch breaking changes before they affect users
- Faster recovery from bad deployments
- Increased confidence in auto-updates

---

### 5. Update Scheduling / Maintenance Windows

**Problem:** Updates can happen during peak gaming hours (if using webhooks).

**Solution:** Add maintenance window configuration

```bash
# Add to .env or config
UPDATE_ALLOWED_HOURS="2-6"  # Only allow updates between 2 AM and 6 AM
UPDATE_BLACKOUT_DAYS="Friday,Saturday"  # No updates on gaming nights

# Enhanced check_for_updates() in run_python_script.sh
is_maintenance_window() {
    current_hour=$(date +%H)
    current_day=$(date +%A)

    # Check blackout days
    if echo "$UPDATE_BLACKOUT_DAYS" | grep -qi "$current_day"; then
        log "⏸️ Update blocked: Blackout day ($current_day)"
        return 1
    fi

    # Check allowed hours
    IFS='-' read -r start_hour end_hour <<< "$UPDATE_ALLOWED_HOURS"
    if [ "$current_hour" -ge "$start_hour" ] && [ "$current_hour" -lt "$end_hour" ]; then
        return 0  # In maintenance window
    else
        log "⏸️ Update blocked: Outside maintenance window (${start_hour}:00-${end_hour}:00)"
        return 1
    fi
}

apply_updates() {
    # Check if we're in maintenance window
    if ! is_maintenance_window; then
        log "⏸️ Updates pending - waiting for maintenance window"
        # Mark updates as pending
        echo "$(git rev-parse origin/main)" > .pending_update
        return 1
    fi

    # ... rest of update logic
}
```

**Benefits:**
- Updates don't interrupt peak gaming hours
- More predictable maintenance schedule
- Users know when to expect downtime

---

### 6. Enhanced Health Checks

**Problem:** Health check is basic (process exists + file timestamp).

**Solution:** Implement comprehensive health monitoring

```python
# health_check.py - Comprehensive bot health monitoring
import asyncio
import aiohttp
import time
from pathlib import Path
from database import get_db

HEALTH_FILE = Path(".bot_health")

async def perform_health_check():
    """Comprehensive health check with multiple validation points"""
    health_status = {
        "healthy": True,
        "checks": {},
        "timestamp": time.time()
    }

    try:
        # Check 1: Database responsive
        try:
            db = get_db()
            start = time.time()
            db.cursor().execute("SELECT 1")
            latency = (time.time() - start) * 1000

            health_status["checks"]["database"] = {
                "status": "ok",
                "latency_ms": round(latency, 2)
            }
        except Exception as e:
            health_status["healthy"] = False
            health_status["checks"]["database"] = {"status": "error", "error": str(e)}

        # Check 2: Discord connection
        try:
            # This would be called from within the bot
            # For external script, check if bot is responding to Discord
            from bot import bot
            latency = bot.latency * 1000 if bot.latency else 0

            health_status["checks"]["discord"] = {
                "status": "ok" if bot.is_ready() else "connecting",
                "latency_ms": round(latency, 2),
                "guilds": len(bot.guilds)
            }
        except Exception as e:
            health_status["healthy"] = False
            health_status["checks"]["discord"] = {"status": "error", "error": str(e)}

        # Check 3: Memory usage
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024

            health_status["checks"]["memory"] = {
                "status": "ok" if memory_mb < 500 else "warning",
                "usage_mb": round(memory_mb, 2)
            }
        except:
            pass

        # Write health status
        HEALTH_FILE.write_text(str(int(time.time())))

        return health_status

    except Exception as e:
        health_status["healthy"] = False
        health_status["error"] = str(e)
        return health_status

# Run from bot.py in background task
class ShootyBot(commands.Bot):
    async def setup_hook(self):
        self.bg_task = self.loop.create_task(self.health_check_loop())

    async def health_check_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await perform_health_check()
            await asyncio.sleep(60)  # Every minute
```

**Enhanced bash health check:**
```bash
is_bot_healthy() {
    # Basic check: process running
    if ! pgrep -f "python.*bot.py" >/dev/null; then
        monitor_log "❌ Bot process not found"
        return 1
    fi

    # Health file freshness
    if [ -f "$HEALTH_CHECK_FILE" ]; then
        local last_health=$(stat -c %Y "$HEALTH_CHECK_FILE" 2>/dev/null || echo "0")
        local current_time=$(date +%s)
        local time_diff=$((current_time - last_health))

        if [ $time_diff -gt 180 ]; then  # 3 minutes (was 15)
            monitor_log "❌ Health check stale (${time_diff}s)"
            return 1
        fi
    else
        monitor_log "⚠️ Health file missing"
        return 1
    fi

    # Memory check (prevent memory leaks from crashing Pi)
    local mem_usage=$(ps aux | grep "python.*bot.py" | grep -v grep | awk '{print $4}')
    if (( $(echo "$mem_usage > 50" | bc -l) )); then
        monitor_log "⚠️ High memory usage: ${mem_usage}%"
        # Don't fail, just warn
    fi

    return 0
}
```

**Benefits:**
- Early detection of problems
- More granular health information
- Prevent memory leaks from crashing Pi
- Better debugging information

---

## 💡 Nice-to-Have Improvements (Low Priority)

### 7. Metrics and Monitoring Dashboard

**Problem:** No visibility into update history, success rates, downtime.

**Solution:** Integrate with monitoring service or create simple dashboard

```python
# metrics.py - Simple metrics tracking
import json
from pathlib import Path
from datetime import datetime

METRICS_FILE = Path("metrics.json")

def record_metric(event_type, data):
    """Record deployment metrics"""
    metrics = load_metrics()

    metrics["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "type": event_type,
        "data": data
    })

    # Calculate statistics
    update_events = [e for e in metrics["events"] if e["type"] == "update"]
    metrics["stats"] = {
        "total_updates": len(update_events),
        "successful_updates": len([e for e in update_events if e["data"].get("success")]),
        "failed_updates": len([e for e in update_events if not e["data"].get("success")]),
        "last_update": update_events[-1]["timestamp"] if update_events else None,
        "average_downtime_seconds": calculate_average_downtime(metrics["events"])
    }

    save_metrics(metrics)

# Usage in update script:
record_metric("update_started", {"commit": new_commit})
record_metric("update_completed", {"commit": new_commit, "success": True, "downtime_seconds": 15})
```

**Simple web dashboard:**
```python
# dashboard.py - Simple Flask dashboard for metrics
from flask import Flask, render_template_string
import json

app = Flask(__name__)

@app.route('/metrics')
def metrics():
    with open('metrics.json') as f:
        data = json.load(f)

    return render_template_string("""
    <h1>ShootyBot Metrics</h1>
    <p>Total Updates: {{ stats.total_updates }}</p>
    <p>Success Rate: {{ success_rate }}%</p>
    <p>Last Update: {{ stats.last_update }}</p>
    <p>Average Downtime: {{ stats.average_downtime_seconds }}s</p>

    <h2>Recent Events</h2>
    <ul>
    {% for event in recent_events %}
        <li>{{ event.timestamp }}: {{ event.type }}</li>
    {% endfor %}
    </ul>
    """, stats=data['stats'], recent_events=data['events'][-10:],
         success_rate=round(data['stats']['successful_updates'] / data['stats']['total_updates'] * 100, 1))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

---

### 8. Blue-Green Deployment

**Problem:** Zero-downtime deployments not possible with current approach.

**Solution:** Run two bot instances and switch between them

```bash
# blue_green_deploy.sh - Advanced zero-downtime deployment
BLUE_SCREEN="shooty-blue"
GREEN_SCREEN="shooty-green"
ACTIVE_FILE=".active_instance"

get_active_instance() {
    if [ -f "$ACTIVE_FILE" ]; then
        cat "$ACTIVE_FILE"
    else
        echo "blue"
    fi
}

get_inactive_instance() {
    active=$(get_active_instance)
    if [ "$active" = "blue" ]; then
        echo "green"
    else
        echo "blue"
    fi
}

blue_green_deploy() {
    active=$(get_active_instance)
    inactive=$(get_inactive_instance)

    log "🔄 Blue-Green Deployment: Active=$active, Deploying to=$inactive"

    # Update code in inactive instance directory
    inactive_dir="/home/pi/ShootyBot-${inactive}"
    cd "$inactive_dir"
    git pull origin main

    # Start inactive instance
    screen -dmS "shooty-${inactive}" ./run.sh
    sleep 10

    # Health check on new instance
    if is_instance_healthy "$inactive"; then
        log "✅ New instance healthy - switching traffic"

        # Stop old instance
        screen -S "shooty-${active}" -X quit

        # Mark new instance as active
        echo "$inactive" > "$ACTIVE_FILE"

        log "✅ Deployment complete - now running on $inactive"
    else
        log "❌ New instance unhealthy - keeping $active"
        screen -S "shooty-${inactive}" -X quit
        return 1
    fi
}
```

**Note:** This requires more complex setup (two directories, shared database, etc.)

---

### 9. Feature Flags

**Problem:** Can't test new features in production without full deployment.

**Solution:** Add feature flag system

```python
# feature_flags.py - Simple feature flag system
import json
from pathlib import Path

FLAGS_FILE = Path("feature_flags.json")

class FeatureFlags:
    _flags = {}

    @classmethod
    def load(cls):
        if FLAGS_FILE.exists():
            cls._flags = json.loads(FLAGS_FILE.read_text())
        else:
            cls._flags = {
                "valorant_match_tracking": True,
                "cross_server_sessions": True,
                "experimental_stats": False,
                "new_ui_redesign": False
            }
            cls.save()

    @classmethod
    def is_enabled(cls, flag_name, default=False):
        return cls._flags.get(flag_name, default)

    @classmethod
    def enable(cls, flag_name):
        cls._flags[flag_name] = True
        cls.save()

    @classmethod
    def disable(cls, flag_name):
        cls._flags[flag_name] = False
        cls.save()

    @classmethod
    def save(cls):
        FLAGS_FILE.write_text(json.dumps(cls._flags, indent=2))

# Usage in bot code:
if FeatureFlags.is_enabled("experimental_stats"):
    # Show experimental stats
    pass

# Admin command to toggle features:
@commands.command()
@commands.has_permissions(administrator=True)
async def toggle_feature(ctx, flag_name: str):
    """Toggle a feature flag"""
    if FeatureFlags.is_enabled(flag_name):
        FeatureFlags.disable(flag_name)
        await ctx.send(f"❌ Disabled: {flag_name}")
    else:
        FeatureFlags.enable(flag_name)
        await ctx.send(f"✅ Enabled: {flag_name}")
```

---

### 10. Automated Changelog Generation

**Problem:** No record of what changed in each update.

**Solution:** Auto-generate changelog from git commits

```bash
# generate_changelog.sh - Auto-generate changelog for updates
generate_changelog() {
    local from_commit=$1
    local to_commit=$2

    echo "# Changelog for $(git rev-parse --short $to_commit)"
    echo ""
    echo "**Deployed:** $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Get commit messages
    echo "## Changes"
    git log --pretty=format:"- %s (%an)" $from_commit..$to_commit
    echo ""
    echo ""

    # Get file changes
    echo "## Files Changed"
    git diff --name-status $from_commit $to_commit | head -20
    echo ""

    # Get stats
    echo "## Statistics"
    git diff --shortstat $from_commit $to_commit
}

# Usage in update script:
CHANGELOG=$(generate_changelog "$PREVIOUS_COMMIT" "$NEW_COMMIT")
echo "$CHANGELOG" >> changelogs/$(date +%Y%m%d_%H%M%S).md

# Send to Discord
send_discord_alert "📝 Update deployed:\n\`\`\`$CHANGELOG\`\`\`"
```

---

## 🔒 Security Improvements

### 11. Webhook Security Enhancements

**Current Issue:** Webhook listener exposed to internet with basic security.

**Improvements:**

```python
# Enhanced webhook_listener.py
import ipaddress
from functools import wraps

# GitHub's webhook IP ranges (update periodically)
GITHUB_WEBHOOK_IPS = [
    "192.30.252.0/22",
    "185.199.108.0/22",
    "140.82.112.0/20",
    "143.55.64.0/20",
]

def verify_github_ip(func):
    """Decorator to verify request comes from GitHub"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        client_ip = self.client_address[0]

        # Check if IP is in GitHub's ranges
        is_github = False
        for ip_range in GITHUB_WEBHOOK_IPS:
            if ipaddress.ip_address(client_ip) in ipaddress.ip_network(ip_range):
                is_github = True
                break

        if not is_github:
            logger.warning(f"Rejected webhook from non-GitHub IP: {client_ip}")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Forbidden')
            return

        return func(self, *args, **kwargs)
    return wrapper

class WebhookHandler(BaseHTTPRequestHandler):
    @verify_github_ip
    def do_POST(self):
        # ... existing webhook handling
        pass
```

**Add rate limiting:**
```python
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, identifier):
        now = time.time()
        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.window_seconds
        ]

        if len(self.requests[identifier]) >= self.max_requests:
            return False

        self.requests[identifier].append(now)
        return True

rate_limiter = RateLimiter(max_requests=5, window_seconds=60)

# In webhook handler:
if not rate_limiter.is_allowed(self.client_address[0]):
    logger.warning(f"Rate limit exceeded: {self.client_address[0]}")
    self.send_response(429)
    self.end_headers()
    return
```

---

### 12. Secrets Management

**Problem:** Bot token and API keys in .env file on disk.

**Solution:** Use encrypted secrets or environment-specific vaults

```bash
# secrets_manager.sh - Simple encrypted secrets
encrypt_secrets() {
    # Encrypt .env file with GPG
    gpg --symmetric --cipher-algo AES256 .env
    rm .env
    echo "✅ Secrets encrypted to .env.gpg"
}

decrypt_secrets() {
    # Decrypt at runtime
    gpg --quiet --batch --yes --decrypt --passphrase="$SECRETS_PASSWORD" \
        --output .env .env.gpg
}

# In run_python_script.sh before starting bot:
if [ -f ".env.gpg" ] && [ -n "$SECRETS_PASSWORD" ]; then
    decrypt_secrets
fi
```

**Or use systemd-creds (Raspberry Pi OS with systemd):**
```bash
# Store encrypted credentials in systemd
systemd-creds encrypt --name=bot-token - - < token.txt > /etc/credstore/bot-token.cred

# Load in service file
[Service]
LoadCredential=bot-token:/etc/credstore/bot-token.cred
ExecStart=/bin/bash -c 'BOT_TOKEN=$(cat ${CREDENTIALS_DIRECTORY}/bot-token) python3 bot.py'
```

---

## 📊 Recommended Priority Order

Based on impact vs effort:

1. **Implement immediately:**
   - #2: Discord Notifications (easy, high value)
   - #1: Automatic Rollback (medium effort, critical)
   - #6: Enhanced Health Checks (easy, high value)

2. **Implement soon:**
   - #3: Graceful Shutdown (medium effort, better UX)
   - #5: Maintenance Windows (easy, prevents prime-time outages)
   - #4: Pre-deployment Testing (medium effort, prevents issues)

3. **Implement later:**
   - #11: Webhook Security (if using webhooks)
   - #7: Metrics Dashboard (nice visibility)
   - #10: Changelog Generation (nice documentation)

4. **Consider for future:**
   - #8: Blue-Green Deployment (complex, true zero-downtime)
   - #9: Feature Flags (useful for experimentation)
   - #12: Secrets Management (important for sensitive deployments)

---

## Quick Wins (Implement Today)

Here are 3 improvements you can implement in under 30 minutes:

### Quick Win #1: Discord Notifications (10 minutes)

```bash
# Add to .env
DISCORD_ADMIN_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE

# Add to run_python_script.sh (top of file after config)
send_discord_alert() {
    local message=$1
    if [ -n "$DISCORD_ADMIN_WEBHOOK_URL" ]; then
        curl -H "Content-Type: application/json" \
             -d "{\"content\": \"$message\"}" \
             "$DISCORD_ADMIN_WEBHOOK_URL" 2>/dev/null
    fi
}

# Add after successful update (line 71)
send_discord_alert "✅ ShootyBot updated to $(git rev-parse --short HEAD)"

# Add after failed update (line 73)
send_discord_alert "❌ ShootyBot update failed - check logs"
```

### Quick Win #2: Database Backup Before Updates (5 minutes)

```bash
# Add to apply_updates() before git pull (line 58)
if [ -f "shooty_bot.db" ]; then
    cp shooty_bot.db "shooty_bot.db.backup.$(date +%Y%m%d_%H%M%S)"
    log "📦 Database backup created"
    # Keep only last 5 backups
    ls -t shooty_bot.db.backup.* 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null
fi
```

### Quick Win #3: Commit Hash in Logs (2 minutes)

```bash
# Add to start_bot() after successful start (line 138)
monitor_log "ℹ️ Running version: $(git rev-parse --short HEAD)"
```

---

## Summary

**Most impactful improvements:**
1. Automatic rollback on failures → Prevents extended outages
2. Discord notifications → Instant visibility
3. Graceful shutdown → Better user experience
4. Enhanced health checks → Earlier problem detection
5. Maintenance windows → Avoid prime-time disruptions

**Implementation strategy:**
- Start with quick wins (30 min total)
- Add rollback + notifications (2-3 hours)
- Add graceful shutdown (1-2 hours)
- Consider others based on your needs

Would you like me to implement any of these improvements for you?
