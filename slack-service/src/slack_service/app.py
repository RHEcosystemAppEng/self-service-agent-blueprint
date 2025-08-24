import os
from pathlib import Path
from flask import Flask, request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier

from session_manager.SessionManager import SessionManager
from asset_manager.agent_manager import AgentManager
from asset_manager.util import load_config_from_path


# Initialize Flask app
app = Flask(__name__)

# Initialize Slack client and verifier
client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
signature_verifier = SignatureVerifier(os.environ.get("SLACK_SIGNING_SECRET"))

# Load configuration and initialize AgentManager
config = load_config_from_path(Path("asset_manager/config"))
agent_manager = AgentManager(config)

# Initialize SessionManager
session_manager = SessionManager(
    agent_manager=agent_manager,
    available_agents=agent_manager.agents(),
)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Route for handling Slack events.
    This function is the entry point for all events from Slack.
    """
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

            response_text = session_manager.handle_user_message(
                user_id, text, user_email
            )

            try:
                client.chat_postMessage(channel=channel_id, text=response_text)
            except SlackApiError as e:
                print(f"Error posting message: {e}")

    return "OK", 200


if __name__ == "__main__":
    app.run(port=3000)