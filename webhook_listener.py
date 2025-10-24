#!/usr/bin/env python3
"""
GitHub Webhook Listener for ShootyBot Auto-Updates

This script listens for GitHub webhook events and triggers immediate bot updates
when changes are pushed to the main branch, instead of waiting for the daily 5 AM check.

Setup:
1. Configure port forwarding on your router: External port → Pi's port 9000
2. Add webhook in GitHub repo settings:
   - URL: http://your-public-ip:9000/update
   - Content type: application/json
   - Secret: (set WEBHOOK_SECRET below)
   - Events: Just the push event
3. Run as service or in screen session

Security:
- Set WEBHOOK_SECRET to match GitHub webhook secret
- Consider using nginx reverse proxy with SSL
- Limit access to webhook endpoint via firewall rules
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json
import hmac
import hashlib
import os
import logging
from pathlib import Path

# Configuration
WEBHOOK_PORT = 9000
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')  # Set in .env or environment
BOT_DIR = Path(__file__).parent.absolute()
UPDATE_SCRIPT = BOT_DIR / 'run_python_script.sh'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(BOT_DIR / 'webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle GitHub webhook POST requests"""

    def log_message(self, format, *args):
        """Override to use logger instead of stderr"""
        logger.info(format % args)

    def verify_signature(self, payload):
        """Verify GitHub webhook signature for security"""
        if not WEBHOOK_SECRET:
            logger.warning("No WEBHOOK_SECRET set - signature verification disabled")
            return True

        signature_header = self.headers.get('X-Hub-Signature-256')
        if not signature_header:
            logger.error("No signature header found")
            return False

        # Compute expected signature
        expected_signature = 'sha256=' + hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(expected_signature, signature_header)

    def do_POST(self):
        """Handle POST requests from GitHub webhooks"""
        if self.path != '/update':
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')
            return

        try:
            # Read payload
            content_length = int(self.headers.get('Content-Length', 0))
            payload = self.rfile.read(content_length)

            # Verify signature for security
            if not self.verify_signature(payload):
                logger.error("Invalid webhook signature")
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'Invalid signature')
                return

            # Parse webhook data
            data = json.loads(payload)
            event = self.headers.get('X-GitHub-Event')

            logger.info(f"Received {event} event from GitHub")

            # Check if this is a push to main branch
            if event == 'push' and data.get('ref') == 'refs/heads/main':
                repo_name = data.get('repository', {}).get('full_name')
                pusher = data.get('pusher', {}).get('name')
                commits = len(data.get('commits', []))

                logger.info(f"Push to main detected: {repo_name} by {pusher} ({commits} commits)")
                logger.info("Triggering bot update...")

                # Trigger update script
                result = subprocess.Popen(
                    [str(UPDATE_SCRIPT), '--force-update'],
                    cwd=str(BOT_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                logger.info(f"Update process started with PID {result.pid}")

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'success',
                    'message': 'Update triggered',
                    'commits': commits,
                    'pusher': pusher
                }
                self.wfile.write(json.dumps(response).encode())
                return

            # Other events or branches - acknowledge but don't update
            logger.info(f"Ignoring {event} event (not a push to main)")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Event acknowledged')

        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Internal server error')

    def do_GET(self):
        """Handle GET requests (health check)"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                'status': 'running',
                'webhook_port': WEBHOOK_PORT,
                'secret_configured': bool(WEBHOOK_SECRET)
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')


def main():
    """Start the webhook listener server"""
    if not UPDATE_SCRIPT.exists():
        logger.error(f"Update script not found: {UPDATE_SCRIPT}")
        logger.error("Please ensure run_python_script.sh exists in the bot directory")
        return

    server_address = ('0.0.0.0', WEBHOOK_PORT)
    httpd = HTTPServer(server_address, WebhookHandler)

    logger.info("=" * 60)
    logger.info("ShootyBot Webhook Listener Started")
    logger.info("=" * 60)
    logger.info(f"Listening on port: {WEBHOOK_PORT}")
    logger.info(f"Bot directory: {BOT_DIR}")
    logger.info(f"Update script: {UPDATE_SCRIPT}")
    logger.info(f"Webhook secret: {'configured' if WEBHOOK_SECRET else 'NOT SET (insecure!)'}")
    logger.info("")
    logger.info("Configure GitHub webhook:")
    logger.info(f"  URL: http://YOUR_PUBLIC_IP:{WEBHOOK_PORT}/update")
    logger.info("  Content type: application/json")
    logger.info("  Events: Just the push event")
    logger.info("")
    logger.info("Health check: http://YOUR_PUBLIC_IP:{WEBHOOK_PORT}/health")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down webhook listener...")
        httpd.shutdown()


if __name__ == '__main__':
    main()
