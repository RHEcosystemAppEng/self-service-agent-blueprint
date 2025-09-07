import uuid
from pathlib import Path
from asset_manager.agent_manager import AgentManager
from asset_manager.util import load_config_from_path


class SessionManager:
    """
    Manages user sessions and conversations with agents.
    """
    ROUTING_AGENT_NAME = "routing-agent"
    def __init__(self, agent_manager):
        """
        Initializes the SessionManager.

        Args:
            agent_manager: An initialized AgentManager instance.
        """
        self.agent_manager = agent_manager
        self.agents = agent_manager.agents()
        self.user_sessions = {}

    def _generate_session_name(self, user_id: str, agent_name: str = None) -> str:
        """Generate a unique session name"""
        unique_id = str(uuid.uuid4())[:8]  # First 8 characters of UUID

        if agent_name:
            return f"slack-session-{user_id}-{agent_name}-{unique_id}"
        else:
            return f"slack-session-{user_id}-{unique_id}"

    def send_message_to_agent(
        self, agent_id: str, session_id: str, message: str
    ) -> str:
        """Send a message to an agent and return the response"""
        try:
            response_stream = self.agent_manager.create_agent_turn(
                agent_id=agent_id,
                session_id=session_id,
                stream=True,
                messages=[{"role": "user", "content": message}],
            )

            response = ""
            for chunk in response_stream:
                if hasattr(chunk, "error") and chunk.error:
                    error_message = chunk.error.get("message", "Unknown agent error")
                    print(f"Error from agent API: {error_message}")
                    return f"Error from agent: {error_message}"

                if (
                    hasattr(chunk, "event")
                    and hasattr(chunk.event, "payload")
                    and chunk.event.payload.event_type == "turn_complete"
                    and hasattr(chunk.event.payload.turn, "output_message")
                ):
                    turn = chunk.event.payload.turn
                    stop_reason = turn.output_message.stop_reason

                    if stop_reason == "end_of_turn":
                        response += turn.output_message.content
                    else:
                        print(f"Agent turn stopped for reason: {stop_reason}")

            return response.strip()

        except Exception as e:
            print(f"Error in send_message_to_agent: {e}")
            return f"Error: {str(e)}"

    def _route_to_specialist(self, user_id, agent_name, text, current_session):
        """Routes the conversation to a specialist agent."""
        print(f"Routing to agent: {agent_name}")
        new_agent_id = self.agents[agent_name]

        # Create a new session for the specialist agent
        session_name = self._generate_session_name(user_id, agent_name)
        new_session = self.agent_manager.create_session(
            new_agent_id, session_name=session_name
        )

        # Update the current session to the new specialist agent
        current_session["agent_id"] = new_agent_id
        current_session["session_id"] = new_session.session_id

        # Send the message to the new agent
        agent_response = self.send_message_to_agent(
            new_agent_id, current_session["session_id"], text
        )

        return agent_response

    def handle_user_message(
        self, user_id: str, text: str, user_email: str = None
    ) -> str:
        """
        Handles an incoming message, manages sessions and history, and returns a response.
        """
        if user_id not in self.user_sessions:
            routing_agent_id = self.agents.get(self.ROUTING_AGENT_NAME)
            if not routing_agent_id:
                return "Error: Core routing agent not available."

            session_name = self._generate_session_name(user_id)
            session = self.agent_manager.create_session(
                routing_agent_id, session_name=session_name
            )
            self.user_sessions[user_id] = {
                "agent_id": routing_agent_id,
                "session_id": session.session_id,
                "email": user_email,
            }
            print(f"New session for user {user_id} ({user_email})")

        current_session = self.user_sessions[user_id]

        agent_response = self.send_message_to_agent(
            current_session["agent_id"],
            current_session["session_id"],
            text,
        )

        potential_agent_name = agent_response.strip()
        if (
            potential_agent_name in self.agents
            and potential_agent_name != self.ROUTING_AGENT_NAME
            and current_session["agent_id"] == self.agents.get(self.ROUTING_AGENT_NAME)
        ):
            return self._route_to_specialist(
                user_id, potential_agent_name, text, current_session
            )

        return agent_response

    def reset_user_session(self, user_id: str):
        """
        Removes a user's session from the session manager.
        """
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
            print(f"Session for user {user_id} has been reset.")
            return True
        return False


def create_session_manager():
    """
    Factory function to load config, initialize an AgentManager,
    and return a fully configured SessionManager instance.
    """
    # Use absolute path since we might be running from different working directory
    config_path = Path("/app/asset-manager/config")
    if not config_path.exists():
        config_path = Path("asset_manager/config")  # fallback to relative path
    
    config = load_config_from_path(config_path)
    agent_manager = AgentManager(config)
    session_manager = SessionManager(agent_manager=agent_manager)
    
    return session_manager