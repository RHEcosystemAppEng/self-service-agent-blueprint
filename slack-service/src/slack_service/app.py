import os
from flask import Flask, request
from session_manager.session_manager import create_session_manager
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

# Create Session Manager
session_manager = create_session_manager()

def create_app(config_path="asset_manager/config"):
    """Creates and configures a new instance of the Flask application."""

    # Initialize Slack Bolt app
    slack_app = App(
        token=os.environ.get("SLACK_BOT_TOKEN"),
        signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
    )

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
            say(text="Your conversation history has been cleared. We can start fresh!")
        else:
            say(text="You didn't have an active session to clear, but we can start one now!")

    # Initialize Flask app
    app = Flask(__name__)
    handler = SlackRequestHandler(slack_app)

    @app.route("/slack/events", methods=["POST"])
    def slack_events():
        """Route for handling Slack events using Bolt framework."""
        return handler.handle(request)

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "agents": len(session_manager.agents)}, 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=3000)
