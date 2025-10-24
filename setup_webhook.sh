#!/bin/bash

# Setup script for ShootyBot GitHub Webhook Listener
# This enables instant updates when you push to GitHub instead of waiting for daily check

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBHOOK_SCREEN="shooty-webhook"

echo "🔧 Setting up ShootyBot GitHub Webhook Listener..."
echo "📂 Script directory: ${SCRIPT_DIR}"
echo ""

# Check if webhook_listener.py exists
if [ ! -f "${SCRIPT_DIR}/webhook_listener.py" ]; then
    echo "❌ webhook_listener.py not found"
    exit 1
fi

# Make webhook listener executable
chmod +x "${SCRIPT_DIR}/webhook_listener.py"

echo "Would you like to:"
echo "  1) Run webhook listener in screen (simple, recommended)"
echo "  2) Install as systemd service (requires sudo)"
echo "  3) Just show setup instructions"
read -p "Choose option [1-3]: " choice

case $choice in
    1)
        # Screen-based setup
        echo ""
        echo "🚀 Starting webhook listener in screen session..."

        # Kill any existing webhook screen session
        if screen -list | grep -q "${WEBHOOK_SCREEN}"; then
            echo "🛑 Stopping existing webhook listener..."
            screen -S "${WEBHOOK_SCREEN}" -X quit
            sleep 2
        fi

        # Start webhook listener in screen
        screen -dmS "${WEBHOOK_SCREEN}" python3 "${SCRIPT_DIR}/webhook_listener.py"
        sleep 2

        if screen -list | grep -q "${WEBHOOK_SCREEN}"; then
            echo "✅ Webhook listener started successfully!"
            echo ""
            echo "📋 Commands:"
            echo "   screen -r ${WEBHOOK_SCREEN}  # View webhook listener"
            echo "   Ctrl+A then D               # Detach from screen"
            echo "   tail -f webhook.log         # View webhook logs"
            echo ""
        else
            echo "❌ Failed to start webhook listener"
            exit 1
        fi
        ;;

    2)
        # Systemd-based setup
        echo ""
        echo "🔧 Installing systemd service..."

        # Create service file
        SERVICE_FILE="/etc/systemd/system/webhook-listener.service"
        sudo sed "s#<PATH_TO_SHOOTYBOT>#${SCRIPT_DIR}#g;s#<BOT_USER>#${USER}#g" \
            "${SCRIPT_DIR}/deploy/webhook-listener.service" | \
            sudo tee "$SERVICE_FILE" >/dev/null

        # Reload systemd and start service
        sudo systemctl daemon-reload
        sudo systemctl enable webhook-listener.service
        sudo systemctl start webhook-listener.service

        echo "✅ Webhook listener service installed!"
        echo ""
        echo "📋 Commands:"
        echo "   sudo systemctl status webhook-listener   # Check status"
        echo "   sudo systemctl restart webhook-listener  # Restart service"
        echo "   sudo journalctl -u webhook-listener -f  # View logs"
        echo ""
        ;;

    3)
        # Just show instructions
        echo ""
        ;;

    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

echo "=" * 70
echo "📋 GitHub Webhook Configuration Instructions"
echo "=" * 70
echo ""
echo "1. Find your Raspberry Pi's public IP address:"
echo "   Visit: https://whatismyipaddress.com (from your Pi's network)"
echo ""
echo "2. Configure port forwarding on your router:"
echo "   - External port: 9000"
echo "   - Internal IP: Your Pi's local IP (usually 192.168.x.x)"
echo "   - Internal port: 9000"
echo "   - Protocol: TCP"
echo ""
echo "3. Add webhook in GitHub repository settings:"
echo "   - Go to: https://github.com/shadohead/ShootyBot/settings/hooks"
echo "   - Click 'Add webhook'"
echo "   - Payload URL: http://YOUR_PUBLIC_IP:9000/update"
echo "   - Content type: application/json"
echo "   - Secret: (optional, set WEBHOOK_SECRET in .env)"
echo "   - SSL verification: Disable (unless using reverse proxy)"
echo "   - Events: Just the push event"
echo "   - Active: ✓"
echo ""
echo "4. Test the webhook:"
echo "   - Push a commit to main branch"
echo "   - Check webhook.log for activity"
echo "   - GitHub webhook page will show delivery status"
echo ""
echo "5. Optional: Set webhook secret for security:"
echo "   echo 'WEBHOOK_SECRET=your-random-secret-here' >> .env"
echo ""
echo "⚠️  Security Notes:"
echo "   - Webhook listener is exposed to the internet"
echo "   - Consider using a reverse proxy with SSL (nginx)"
echo "   - Set WEBHOOK_SECRET for better security"
echo "   - Monitor webhook.log regularly"
echo ""
echo "🔍 Test webhook health:"
echo "   curl http://YOUR_PUBLIC_IP:9000/health"
echo ""
echo "=" * 70

echo ""
echo "✅ Setup complete! Your bot will now update instantly when you merge to main."
echo ""
