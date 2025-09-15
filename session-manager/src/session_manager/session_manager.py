from pathlib import Path

from asset_manager.agent_manager import AgentManager
from asset_manager.util import load_config_from_path

from .session_manager_base import SessionManagerBase


class SessionManager(SessionManagerBase):
    """
    Manages user sessions and conversations with agents using AgentManager.
    """

    def __init__(self, agent_manager):
        """
        Initializes the SessionManager.

        Args:
            agent_manager: An initialized AgentManager instance.
        """
        super().__init__(agent_manager)

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

            return self._process_agent_response(response)

        except Exception as e:
            return self._handle_agent_error(e)

    def _build_initial_session_data(
        self, routing_agent, session, session_name: str, user_email: str
    ) -> dict:
        """Build initial session data structure for a new user."""
        return {
            "agent_id": routing_agent,
            "agent_name": self.ROUTING_AGENT_NAME,  # Add agent_name for consistency
            "session_id": session.session_id,
            "email": user_email,
        }

    def _send_message_to_current_session(self, current_session, text: str) -> str:
        """Send message to the current session and return response"""
        return self.send_message_to_agent(
            current_session["agent_id"],
            current_session["session_id"],
            text,
        )

    def _cleanup_session(self, session_info):
        """Clean up session-specific resources"""
        # No special cleanup needed for AgentManager sessions
        pass

    def _get_agent_for_routing(self, agent_name: str):
        """Get the agent object/identifier for routing."""
        return self.agents.get(agent_name)

    def _create_session_for_agent(
        self, agent, agent_name: str, user_id: str, session_name: str = None, **kwargs
    ):
        """Create a new session for the given agent."""
        if not session_name:
            session_name = self._generate_session_name(user_id, agent_name)
        return self.agent_manager.create_session(agent, session_name=session_name)

    def _build_session_data(
        self, agent, agent_name: str, session, session_name: str
    ) -> dict:
        """Build session data dictionary for updating current session."""
        return {
            "agent_id": agent,
            "agent_name": agent_name,  # Add agent_name for consistency
            "session_id": session.session_id,
        }

    def _update_session_fields(self, current_session, session_data):
        """Update the current session fields with new session data."""
        current_session["agent_id"] = session_data["agent_id"]
        current_session["agent_name"] = session_data["agent_name"]
        current_session["session_id"] = session_data["session_id"]


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
