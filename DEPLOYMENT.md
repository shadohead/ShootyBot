# ShootyBot Raspberry Pi Deployment Guide

This guide explains how to deploy ShootyBot on a Raspberry Pi with automatic updates when you merge changes to GitHub.

## Overview

ShootyBot includes a complete CI/CD-like auto-update system that:
- ✅ Auto-starts bot on system reboot
- ✅ Monitors bot health every 15 minutes
- ✅ Auto-restarts if bot crashes
- ✅ Checks for GitHub updates daily at 5 AM
- ✅ Automatically pulls updates and restarts when changes are merged
- ✅ Updates dependencies if requirements.txt changes
- ✅ Comprehensive logging for monitoring

## Initial Setup on Raspberry Pi

### 1. Clone and Configure

```bash
# Clone the repository
cd ~
git clone https://github.com/shadohead/ShootyBot.git
cd ShootyBot

# Switch to main branch (production)
git checkout main
git pull origin main

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your BOT_TOKEN and other settings
```

### 2. Test Bot Manually

```bash
# Test that the bot runs correctly
./run.sh

# If it works, press Ctrl+C to stop
```

### 3. Setup Auto-Update System

**Option A: Cron-based (Recommended)**

```bash
# Run the setup script
./setup_auto_update.sh

# Start the bot
./run_python_script.sh --start

# Verify it's running
screen -r shooty  # Press Ctrl+A then D to detach
```

**Option B: Systemd-based (Requires root)**

```bash
# Install systemd services
sudo ./setup_systemd.sh $USER

# Check status
systemctl status shootybot
systemctl status shootybot-update.timer
```

## How Auto-Updates Work

### Daily Update Check (5 AM)

1. **Fetch from GitHub**: `git fetch origin main`
2. **Compare commits**: Check if remote has new commits
3. **If updates found**:
   - Stop the bot gracefully
   - Pull latest changes: `git pull origin main`
   - Update dependencies if needed
   - Restart the bot
4. **Log everything**: Check `update.log` for details

### Health Monitoring (Every 15 minutes)

1. **Check bot process**: Verify Python process is running
2. **Check health file**: Ensure bot is responding
3. **Auto-restart if needed**: Restart bot if health check fails
4. **Log status**: Check `monitor.log` for details

## Workflow: Development to Production

### Your Development Workflow

```bash
# 1. Create feature branch (on your dev machine)
git checkout -b feature/my-new-feature

# 2. Make changes and commit
git add .
git commit -m "Add new feature"

# 3. Push to GitHub
git push origin feature/my-new-feature

# 4. Create Pull Request on GitHub
#    Review and merge to main branch

# 5. Raspberry Pi automatically updates!
#    - Next health check (within 15 minutes): Ensures bot is running
#    - Next daily check (5 AM): Pulls updates and restarts
```

### Instant Updates (Optional)

If you want updates immediately after merging instead of waiting until 5 AM:

```bash
# SSH into your Raspberry Pi and run:
cd ~/ShootyBot
./run_python_script.sh --force-update
```

Or set up a GitHub webhook (see Advanced Setup below).

## Manual Control Commands

### Start/Stop/Restart

```bash
# Start the bot
./run_python_script.sh --start

# Check health status
./run_python_script.sh --monitor

# Force update check and apply
./run_python_script.sh --force-update

# Check for updates without applying
./run_python_script.sh --check-only

# Access bot console
screen -r shooty

# Stop the bot (from within screen)
Ctrl+C

# Stop the bot (from outside screen)
screen -S shooty -X quit
```

### Monitoring

```bash
# View update logs (real-time)
tail -f update.log

# View health check logs (real-time)
tail -f monitor.log

# View cron execution logs (real-time)
tail -f cron.log

# View bot output
screen -r shooty  # Ctrl+A then D to detach without stopping
```

## Troubleshooting

### Bot Not Starting

```bash
# Check if bot is running
pgrep -f "python.*bot.py"

# Check screen sessions
screen -list

# Check logs
tail -50 monitor.log

# Try manual start
./run.sh
```

### Updates Not Applying

```bash
# Check update logs
tail -50 update.log

# Manually check for updates
./run_python_script.sh --check-only

# Force update
./run_python_script.sh --force-update

# Verify git status
git status
git log -3

# Check remote connection
git fetch origin main
```

### Health Checks Failing

```bash
# Check monitor logs
tail -50 monitor.log

# Verify process
ps aux | grep python.*bot.py

# Check health file
ls -la .bot_health

# Check screen session
screen -list
```

### Cron Jobs Not Running

```bash
# Check if cron jobs exist
crontab -l | grep run_python_script

# Re-run setup
./setup_auto_update.sh

# Check cron logs
tail -50 cron.log

# Manually test cron commands
cd ~/ShootyBot && ./run_python_script.sh --monitor
```

## Advanced Setup

### Instant Updates via GitHub Webhooks

For immediate updates when you merge to main (instead of waiting until 5 AM):

1. **On Raspberry Pi**: Set up a simple webhook listener

```bash
# Create webhook listener script
cat > webhook_listener.py << 'EOF'
#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json
import os

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/update':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)

            # Parse GitHub webhook
            data = json.loads(body)

            # Check if push to main branch
            if data.get('ref') == 'refs/heads/main':
                print("Update triggered by GitHub push to main")
                subprocess.Popen(['/home/pi/ShootyBot/run_python_script.sh', '--force-update'])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Update triggered')
                return

        self.send_response(404)
        self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9000), WebhookHandler)
    print("Webhook listener running on port 9000")
    server.serve_forever()
EOF

chmod +x webhook_listener.py
```

2. **Configure port forwarding** on your router: Forward port 9000 to your Pi
3. **Add webhook on GitHub**:
   - Go to: `https://github.com/shadohead/ShootyBot/settings/hooks`
   - Add webhook: `http://your-pi-public-ip:9000/update`
   - Content type: `application/json`
   - Event: Just the push event
   - Branch: main

4. **Run webhook listener as service** (optional systemd setup)

### Custom Update Schedule

Edit the cron job to change update frequency:

```bash
# Edit crontab
crontab -e

# Examples:
# Every 6 hours:  0 */6 * * *
# Twice daily:    0 5,17 * * *
# Every hour:     0 * * * *
```

### Update on Specific Branch

If you want to track a different branch (not recommended for production):

```bash
# Edit run_python_script.sh
nano run_python_script.sh

# Change line 32 and 36:
git fetch origin YOUR_BRANCH
REMOTE_HASH=$(git rev-parse origin/YOUR_BRANCH)

# And line 59:
git pull origin YOUR_BRANCH
```

## Security Considerations

1. **Keep .env secure**: Never commit your .env file with tokens
2. **Use SSH keys**: For GitHub authentication
3. **Firewall**: If using webhooks, secure your webhook endpoint
4. **Update Pi regularly**: `sudo apt update && sudo apt upgrade`
5. **Monitor logs**: Check for suspicious activity

## Backup and Recovery

### Backup Data

```bash
# Backup database and config
tar -czf backup-$(date +%Y%m%d).tar.gz shooty_bot.db .env

# Upload to safe location
scp backup-*.tar.gz your-backup-server:/backups/
```

### Recovery

```bash
# If something goes wrong, rollback
git log  # Find last working commit
git reset --hard COMMIT_HASH
./run_python_script.sh --start
```

## Performance Optimization

### Raspberry Pi 3/4 Settings

```bash
# Increase swap for better stability
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Optimize Python
pip install --upgrade pip setuptools wheel
```

## Next Steps

1. ✅ Setup auto-update system: `./setup_auto_update.sh`
2. ✅ Start the bot: `./run_python_script.sh --start`
3. ✅ Verify it's running: `screen -r shooty`
4. ✅ Check logs: `tail -f monitor.log`
5. ✅ Test your workflow: Make a change, merge to main, wait for auto-update

## Support

- **Logs**: Check `update.log`, `monitor.log`, and `cron.log`
- **Manual commands**: See "Manual Control Commands" section above
- **GitHub Issues**: Report problems at https://github.com/shadohead/ShootyBot/issues
