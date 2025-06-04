#!/bin/bash
# Install systemd service and timer for ShootyBot
# Usage: sudo ./setup_systemd.sh [bot-user]

set -e

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_USER="${1:-$USER}"

service_file=/etc/systemd/system/shootybot.service
update_service=/etc/systemd/system/shootybot-update.service
update_timer=/etc/systemd/system/shootybot-update.timer

sudo sed "s#<PATH_TO_SHOOTYBOT>#${BOT_DIR}#g;s#<BOT_USER>#${BOT_USER}#g" deploy/shootybot.service | sudo tee "$service_file" >/dev/null
sudo sed "s#<PATH_TO_SHOOTYBOT>#${BOT_DIR}#g;s#<BOT_USER>#${BOT_USER}#g" deploy/shootybot-update.service | sudo tee "$update_service" >/dev/null
sudo cp deploy/shootybot-update.timer "$update_timer"

sudo systemctl daemon-reload
sudo systemctl enable shootybot.service
sudo systemctl enable shootybot-update.timer
sudo systemctl start shootybot.service
sudo systemctl start shootybot-update.timer

echo "ShootyBot systemd service installed and started."
