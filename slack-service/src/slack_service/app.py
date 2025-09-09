import os

from flask import Flask, request
from session_manager.session_manager import create_session_manager
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler


def create_app(config_path="asset_manager/config"):
    """Creates and configures a new instance of the Flask application."""

    # Create Session Manager (moved inside function to ensure env vars are available)
    session_manager = create_session_manager()

    # Check if Slack integration should be enabled
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
    slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
    slack_enabled = slack_bot_token and slack_signing_secret

    if slack_enabled:
        print("Slack integration enabled - initializing Slack Bolt app")
        # Initialize Slack Bolt app
        slack_app = App(token=slack_bot_token, signing_secret=slack_signing_secret)
    else:
        print("Slack integration disabled - running without Slack features")
        slack_app = None

    # Only set up Slack handlers if Slack is enabled
    if slack_enabled:

        @slack_app.event("message")
        def handle_message_events(body, say, client):
            """Handle incoming message events from Slack."""
            event = body["event"]

            # Skip bot messages
            if "bot_id" in event:
                return

            user_id = event.get("user")
            text = event.get("text")

            # Get user email
            user_email = None
            try:
                user_info = client.users_info(user=user_id)
                user_email = user_info["user"]["profile"]["email"]
            except Exception as e:
                print(f"Error fetching user info: {e}")

            # Process message and respond
            response_text = session_manager.handle_user_message(
                user_id, text, user_email
            )

            say(text=response_text)

        @slack_app.command("/reset")
        def handle_reset_command(ack, say, command):
            """Handle the /reset slash command to clear user's conversation history."""
            ack()
            user_id = command["user_id"]

            if session_manager.reset_user_session(user_id):
                say(
                    text="Your conversation history has been cleared. We can start fresh!"
                )
            else:
                say(
                    text="You didn't have an active session to clear, but we can start one now!"
                )

    # Initialize Flask app
    app = Flask(__name__)

    # Only create Slack handler if Slack is enabled
    if slack_enabled:
        handler = SlackRequestHandler(slack_app)

        @app.route("/slack/events", methods=["POST"])
        def slack_events():
            """Route for handling Slack events using Bolt framework."""
            return handler.handle(request)

    else:

        @app.route("/slack/events", methods=["POST"])
        def slack_events_disabled():
            """Disabled Slack endpoint - returns service unavailable."""
            return {"error": "Slack integration is not enabled"}, 503

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        status = "healthy"
        agents_count = len(session_manager.agents)
        slack_status = "enabled" if slack_enabled else "disabled"
        return {"status": status, "agents": agents_count, "slack": slack_status}, 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=3000)
