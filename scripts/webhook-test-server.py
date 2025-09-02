#!/usr/bin/env python3
"""
Simple webhook test server for testing webhook integrations.
This server receives webhook calls and displays them in a web interface.
"""

import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Global storage for received webhooks
received_webhooks = []


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests - serve the web interface."""
        if self.path == "/":
            self.serve_web_interface()
        elif self.path == "/api/webhooks":
            self.serve_webhook_data()
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests - receive webhook data."""
        self.receive_webhook()

    def do_PUT(self):
        """Handle PUT requests - receive webhook data."""
        self.receive_webhook()

    def do_PATCH(self):
        """Handle PATCH requests - receive webhook data."""
        self.receive_webhook()

    def receive_webhook(self):
        """Receive and store webhook data."""
        try:
            # Get content length
            content_length = int(self.headers.get("Content-Length", 0))

            # Read request body
            post_data = self.rfile.read(content_length)

            # Parse JSON if possible
            try:
                json_data = json.loads(post_data.decode("utf-8"))
            except json.JSONDecodeError:
                json_data = post_data.decode("utf-8")

            # Store webhook data
            webhook_data = {
                "timestamp": datetime.now().isoformat(),
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "data": json_data,
                "query_params": parse_qs(urlparse(self.path).query),
            }

            received_webhooks.append(webhook_data)

            # Keep only last 50 webhooks
            if len(received_webhooks) > 50:
                received_webhooks.pop(0)

            print(f"📨 Received {self.command} webhook at {webhook_data['timestamp']}")
            print(f"   Path: {self.path}")
            print(f"   Headers: {len(self.headers)} headers")
            print(f"   Data: {len(str(json_data))} characters")
            print()

            # Send success response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "success", "message": "Webhook received"}
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            print(f"❌ Error receiving webhook: {e}")
            self.send_error(500)

    def serve_web_interface(self):
        """Serve the web interface."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Webhook Test Server</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header { background: #007bff; color: white; padding: 20px; margin: -20px -20px 20px -20px; border-radius: 8px 8px 0 0; }
        .webhook { border: 1px solid #ddd; margin: 10px 0; border-radius: 4px; overflow: hidden; }
        .webhook-header { background: #f8f9fa; padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold; }
        .webhook-content { padding: 15px; }
        .json-data { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; white-space: pre-wrap; }
        .timestamp { color: #666; font-size: 0.9em; }
        .method { display: inline-block; padding: 2px 8px; border-radius: 3px; color: white; font-size: 0.8em; margin-right: 10px; }
        .method.POST { background: #28a745; }
        .method.PUT { background: #ffc107; color: black; }
        .method.PATCH { background: #17a2b8; }
        .method.GET { background: #6c757d; }
        .refresh-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 10px 0; }
        .refresh-btn:hover { background: #0056b3; }
        .clear-btn { background: #dc3545; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 10px 0; }
        .clear-btn:hover { background: #c82333; }
        .status { padding: 10px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 Webhook Test Server</h1>
            <p>This server receives webhook calls from the Self-Service Agent Integration Dispatcher</p>
        </div>

        <div class="status">
            <strong>Server Status:</strong> Running and ready to receive webhooks
        </div>

        <div>
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
            <button class="clear-btn" onclick="clearWebhooks()">🗑️ Clear All</button>
        </div>

        <div id="webhooks">
            <p>No webhooks received yet. Send a test notification to see webhook data here.</p>
        </div>
    </div>

    <script>
        function clearWebhooks() {
            if (confirm('Are you sure you want to clear all webhooks?')) {
                fetch('/api/clear', {method: 'POST'})
                    .then(() => location.reload());
            }
        }

        function formatWebhook(webhook) {
            return `
                <div class="webhook">
                    <div class="webhook-header">
                        <span class="method ${webhook.method}">${webhook.method}</span>
                        <span class="timestamp">${new Date(webhook.timestamp).toLocaleString()}</span>
                    </div>
                    <div class="webhook-content">
                        <h4>Path: ${webhook.path}</h4>
                        <h5>Headers (${Object.keys(webhook.headers).length}):</h5>
                        <div class="json-data">${JSON.stringify(webhook.headers, null, 2)}</div>
                        <h5>Data:</h5>
                        <div class="json-data">${JSON.stringify(webhook.data, null, 2)}</div>
                    </div>
                </div>
            `;
        }

        function loadWebhooks() {
            fetch('/api/webhooks')
                .then(response => response.json())
                .then(webhooks => {
                    const container = document.getElementById('webhooks');
                    if (webhooks.length === 0) {
                        container.innerHTML = '<p>No webhooks received yet. Send a test notification to see webhook data here.</p>';
                    } else {
                        container.innerHTML = webhooks.map(formatWebhook).join('');
                    }
                });
        }

        // Load webhooks on page load
        loadWebhooks();

        // Auto-refresh every 5 seconds
        setInterval(loadWebhooks, 5000);
    </script>
</body>
</html>
        """

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def serve_webhook_data(self):
        """Serve webhook data as JSON."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(received_webhooks).encode())

    def log_message(self, format, *args):
        """Override to reduce log noise."""
        pass


def start_server(port=8080):
    """Start the webhook test server."""
    server = HTTPServer(("localhost", port), WebhookHandler)

    print("🧪 Webhook Test Server Starting...")
    print(f"   URL: http://localhost:{port}")
    print(f"   Webhook Endpoint: http://localhost:{port}/")
    print(f"   API Endpoint: http://localhost:{port}/api/webhooks")
    print()
    print("📋 Instructions:")
    print("   1. Use this URL in your webhook integration config:")
    print(f"      http://localhost:{port}/")
    print("   2. Send test notifications from the Integration Dispatcher")
    print("   3. View received webhooks in the web interface")
    print("   4. Press Ctrl+C to stop the server")
    print()

    try:
        # Open browser automatically
        threading.Timer(
            1.0, lambda: webbrowser.open(f"http://localhost:{port}")
        ).start()

        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
        server.shutdown()


if __name__ == "__main__":
    import sys

    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 8080.")

    start_server(port)
