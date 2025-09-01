import os
import threading
from pathlib import Path

from asset_manager.agent_manager import AgentManager
from asset_manager.util import load_config_from_path
from flask import Flask, request
from session_manager.session_manager import SessionManager
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier


def create_app(config_path="asset_manager/config"):
    """Creates and configures a new instance of the Flask application."""

    app = Flask(__name__)

    # Initialize Slack client and verifier
    client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
    signature_verifier = SignatureVerifier(os.environ.get("SLACK_SIGNING_SECRET"))

    # Load configuration and initialize AgentManager
    # Use absolute path since we might be running from different working directory
    config_path = Path("/app/asset-manager/config")
    if not config_path.exists():
        config_path = Path("asset_manager/config")  # fallback to relative path
    config = load_config_from_path(config_path)
    agent_manager = AgentManager(config)
    session_manager = SessionManager(agent_manager=agent_manager)

    def process_message(user_id, text, user_email, channel_id):
        """Processes the user message and sends a response back to Slack."""
        response_text = session_manager.handle_user_message(
            user_id, text, user_email
        )
        try:
            client.chat_postMessage(channel=channel_id, text=response_text)
        except SlackApiError as e:
            print(f"Error posting message: {e}")

    @app.route("/slack/events", methods=["POST"])
    def slack_events():
        """Route for handling Slack events."""
        if not signature_verifier.is_valid_request(request.get_data(), request.headers):
            return "Invalid request signature", 403

        if request.json.get("type") == "url_verification":
            return request.json.get("challenge"), 200

        if request.json.get("type") == "event_callback":
            event = request.json.get("event", {})
            event_type = event.get("type")

            if event_type == "message" and "bot_id" not in event:
                user_id = event.get("user")
                text = event.get("text")
                channel_id = event.get("channel")

                try:
                    user_info = client.users_info(user=user_id)
                    user_email = user_info["user"]["profile"]["email"]
                except SlackApiError as e:
                    print(f"Error fetching user info: {e}")
                    user_email = None

                # Run the message processing in a separate thread
                thread = threading.Thread(
                    target=process_message,
                    args=(user_id, text, user_email, channel_id),
                )
                thread.start()

        # Immediately acknowledge the request
        return "OK", 200

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "agents": len(session_manager.agents)}, 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=3000)