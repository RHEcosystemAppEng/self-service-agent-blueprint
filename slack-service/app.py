import os
from flask import Flask, request
from slack_sdk import WebClient
from asset_manager.agent_manager import AgentManager
from llama_stack_client import LlamaStackClient

app = Flask(__name__)

# Initialize Slack Client
slack_token = os.environ.get("SLACK_BOT_TOKEN")
if not slack_token:
    raise ValueError("SLACK_BOT_TOKEN environment variable not set!")
slack_client = WebClient(token=slack_token)

# Initialize Agent Manager
agent_manager = None
available_agents = {}
user_sessions = {}


def initialize_agent_manager():
    """Initialize the agent manager and connect to LlamaStack"""
    global agent_manager, available_agents

    try:
        llama_stack_host = os.environ.get("LLAMASTACK_SERVICE_HOST")
        full_url = f"http://{llama_stack_host}:8321"
        print(f"Connecting to: {full_url}")
        # Create LlamaStack client
        client = LlamaStackClient(base_url=full_url, timeout=600.0)

        # Initialize agent manager
        agent_manager = AgentManager({"timeout": 120})
        agent_manager._client = client

        # Get available agents
        available_agents = agent_manager.agents()
        print("Agent Manager initialized successfully")
        print(f"   Available agents: {list(available_agents.keys())}")

    except Exception as e:
        print(f"Error initializing Agent Manager: {e}")
        raise


def send_message_to_agent(agent_id: str, session_id: str, messages: list) -> str:
    """Send a message to an agent and return the response"""
    try:
        response_stream = agent_manager._client.agents.turn.create(
            agent_id=agent_id,
            session_id=session_id,
            stream=True,
            messages=messages,
        )

        response = ""
        for chunk in response_stream:
            # check if the chunk contains an error attribute before accessing it
            if hasattr(chunk, "error") and chunk.error:
                error_message = chunk.error.get("message", "Unknown agent error")
                print(f"Error from agent API: {error_message}")
                return f"Error from agent: {error_message}"

            # If no error, process the stream for the final message
            if (
                hasattr(chunk, "event")
                and hasattr(chunk.event, "payload")
                and chunk.event.payload.event_type == "turn_complete"
            ):
                if hasattr(chunk.event.payload.turn, "output_message"):
                    content = chunk.event.payload.turn.output_message.content
                    response += content

        return response.strip()

    except Exception as e:
        print(f"Error in send_message_to_agent: {e}")
        return f"Error: {str(e)}"


def handle_user_message(user_id: str, text: str, channel_id: str):
    """Handle incoming user message and route to appropriate agent"""

    # Create or get user session
    if user_id not in user_sessions:
        routing_agent_id = available_agents.get("routing-agent")
        if not routing_agent_id:
            return "Error: Core routing agent not available.", 500

        session = agent_manager._client.agents.session.create(
            routing_agent_id, session_name=f"slack-session-{user_id}"
        )
        user_sessions[user_id] = {
            "agent_id": routing_agent_id,
            "session_id": session.session_id,
        }
        print(f"New session for user {user_id}")

    current_session = user_sessions[user_id]
    messages = [{"role": "user", "content": text}]

    # Get initial response
    agent_response = send_message_to_agent(
        current_session["agent_id"], current_session["session_id"], messages
    )

    # Check if we need to route to a different agent
    potential_agent_name = agent_response.strip()
    if (
        potential_agent_name in available_agents
        and potential_agent_name != "routing-agent"
        and current_session["agent_id"] == available_agents.get("routing-agent")
    ):

        print(f"Routing to agent: {potential_agent_name}")
        new_agent_id = available_agents[potential_agent_name]

        # Create new session with specific agent
        new_session = agent_manager._client.agents.session.create(
            new_agent_id,
            session_name=f"slack-session-{user_id}-{potential_agent_name}",
        )

        # Update user session
        user_sessions[user_id] = {
            "agent_id": new_agent_id,
            "session_id": new_session.session_id,
        }

        # Get response from new agent
        agent_response = send_message_to_agent(
            new_agent_id, new_session.session_id, messages
        )

    # Ensure valid response
    if not agent_response or agent_response.strip() == "":
        agent_response = (
            "I'm sorry, I didn't get a response from the agent. Please try again."
        )

    # Send response to Slack
    slack_client.chat_postMessage(channel=channel_id, text=agent_response)
    return "OK", 200


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle Slack events"""
    data = request.get_json()

    # Handle Slack URL verification
    if "challenge" in data:
        return data["challenge"]

    # Ignore retries and bot messages
    if request.headers.get("X-Slack-Retry-Num") or data.get("event", {}).get("bot_id"):
        return "OK", 200

    # Extract event data
    event = data.get("event", {})
    user_id = event.get("user")
    text = event.get("text")
    channel_id = event.get("channel")

    # Validate required fields
    if not all([user_id, text, channel_id, agent_manager]):
        return "OK", 200

    print(f"Message from user {user_id}: {text}")

    # Process the message
    return handle_user_message(user_id, text, channel_id)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "agents": len(available_agents)}, 200


# Initialize the application
initialize_agent_manager()
