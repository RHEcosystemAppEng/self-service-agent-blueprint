import logging
import uuid
from pathlib import Path

from asset_manager.lg_flow_state_machine import ConversationSession
from asset_manager.responses_agent import ResponsesAgentManager

from .session_manager_base import SessionManagerBase

# Configure logging - suppress INFO messages, only show WARNING and above
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Set this module's logger to WARNING level to suppress INFO messages
logger.setLevel(logging.WARNING)

# Remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)
logging.getLogger("asset_manager").setLevel(logging.WARNING)
logging.getLogger("asset_manager.responses_agent").setLevel(logging.WARNING)
logging.getLogger("asset_manager.lg_flow_state_machine").setLevel(logging.WARNING)


class SessionManagerResponses(SessionManagerBase):
    """
    Manages user sessions and conversations with agents using ResponsesAgentManager.
    """

    def __init__(self, agent_manager, session_name=None):
        """
        Initializes the SessionManagerResponses.

        Args:
            agent_manager: An initialized ResponsesAgentManager instance.
            session_name: Optional session name for resuming existing conversations
        """
        super().__init__(agent_manager)

        # Default checkpoint database path in /tmp
        self.checkpoint_db_path = Path("/tmp/conversation_checkpoints.db")
        self.resume_session_name = session_name

        # Enable session metadata persistence
        self.metadata_file = "/tmp/session_metadata.json"
        self._initialize_metadata()

    def send_message_to_agent(
        self, agent_id: str, session_id: str, message: str
    ) -> str:
        """Send a message to an agent and return the response using ConversationSession"""
        try:
            # Get the conversation session for this user session
            if session_id not in self.user_sessions:
                return "Error: Session not found"

            session_info = self.user_sessions[session_id]
            conversation_session = session_info.get("conversation_session")

            if not conversation_session:
                return "Error: Conversation session not found"

            # Send message using the conversation session
            response = conversation_session.send_message(message)
            return self._process_agent_response(response)

        except Exception as e:
            return self._handle_agent_error(e)

    def _build_initial_session_data(
        self, routing_agent, session, session_name: str, user_email: str
    ) -> dict:
        """Build initial session data structure for a new user."""
        return {
            "agent_name": self.ROUTING_AGENT_NAME,
            "conversation_session": session,
            "session_name": session_name,
            "email": user_email,
        }

    def _send_message_to_current_session(self, current_session, text: str) -> str:
        """Send message to the current session and return response"""
        conversation_session = current_session["conversation_session"]
        response = conversation_session.send_message(text)
        return self._process_agent_response(response)

    def _cleanup_session(self, session_info):
        """Clean up session-specific resources"""
        conversation_session = session_info.get("conversation_session")
        if conversation_session:
            try:
                conversation_session.close()
            except Exception as e:
                logger.error(f"Error closing conversation session: {e}")

    def _get_agent_for_routing(self, agent_name: str):
        """Get the agent object/identifier for routing."""
        return self.agent_manager.get_agent(agent_name)

    def _create_session_for_agent(
        self, agent, agent_name: str, user_id: str, session_name: str = None, **kwargs
    ):
        """Create a new session for the given agent."""
        # Extract parameters from kwargs
        resume_thread_id = kwargs.get("resume_thread_id")
        authoritative_user_id = kwargs.get("authoritative_user_id")

        # Use provided thread_id for resumption or generate a new one
        if resume_thread_id:
            session_thread_id = resume_thread_id
            logger.debug(
                f"Resuming thread ID: {session_thread_id} for agent: {agent_name}"
            )
        else:
            # Generate new thread_id when creating new session
            session_thread_id = str(uuid.uuid4())
            logger.debug(
                f"Starting new conversation with thread ID: {session_thread_id} for agent: {agent_name}"
            )

        return ConversationSession(
            agent,
            session_thread_id,
            str(self.checkpoint_db_path),
            authoritative_user_id=authoritative_user_id,
        )

    def _build_session_data(
        self, agent, agent_name: str, session, session_name: str
    ) -> dict:
        """Build session data dictionary for updating current session."""
        return {
            "agent_name": agent_name,
            "conversation_session": session,
            "session_name": session_name,
        }

    def _create_initial_session(self, user_id: str, user_email: str = None):
        """Create an initial session for a new user, attempting to resume session if provided"""
        # If we have a session name to resume, look up its metadata
        if self.resume_session_name:
            resume_thread_id, target_agent_name = self._get_session_metadata(
                self.resume_session_name
            )
            logger.debug(
                f"Resuming session {self.resume_session_name} -> thread {resume_thread_id}, agent {target_agent_name}"
            )

            if not resume_thread_id:
                logger.info(
                    f"Session '{self.resume_session_name}' not found. Starting fresh..."
                )
                self.resume_session_name = None
                return super()._create_initial_session(user_id, user_email)

            try:
                target_agent = self._get_agent_for_routing(target_agent_name)
                if not target_agent:
                    logger.info(
                        f"Agent '{target_agent_name}' not available. Starting fresh..."
                    )
                    self.resume_session_name = None
                    return super()._create_initial_session(user_id, user_email)

                # Test if the session can be resumed properly
                session = self._create_session_for_agent(
                    target_agent,
                    target_agent_name,
                    user_id,
                    session_name=self.resume_session_name,
                    resume_thread_id=resume_thread_id,
                )

                # For specialist agents, check if the conversation is already completed
                if target_agent_name != self.ROUTING_AGENT_NAME:
                    try:
                        # Try to get the current state - if conversation is completed, start fresh
                        initial_response = session.get_initial_response()
                        if initial_response and (
                            "conversation completed" in initial_response.lower()
                            or "starting new conversation" in initial_response.lower()
                        ):
                            logger.info(
                                f"Session {self.resume_session_name} conversation already completed. Starting fresh with routing agent..."
                            )
                            session.close()
                            self.resume_session_name = None
                            return super()._create_initial_session(user_id, user_email)
                    except Exception:
                        # If there's an error, the thread might be corrupted, start fresh
                        logger.warning(
                            f"Session {self.resume_session_name} appears corrupted. Starting fresh..."
                        )
                        session.close()
                        self.resume_session_name = None
                        return self._create_new_session(user_id, user_email)

                # Build appropriate session data
                if target_agent_name == self.ROUTING_AGENT_NAME:
                    session_data = self._build_initial_session_data(
                        target_agent, session, self.resume_session_name, user_email
                    )
                else:
                    session_data = self._build_session_data(
                        target_agent,
                        target_agent_name,
                        session,
                        self.resume_session_name,
                    )
                    session_data["email"] = user_email

                self.user_sessions[user_id] = session_data
                return

            except Exception as e:
                logger.warning(
                    f"Failed to resume session {self.resume_session_name}: {e}. Starting fresh..."
                )
                self.resume_session_name = None
                return super()._create_initial_session(user_id, user_email)
        else:
            # No session name provided, create new session
            return super()._create_initial_session(user_id, user_email)

    def _update_session_fields(self, current_session, session_data):
        """Update the current session fields with new session data."""
        current_session["agent_name"] = session_data["agent_name"]
        current_session["conversation_session"] = session_data["conversation_session"]
        current_session["session_name"] = session_data["session_name"]

    def reset_user_session(self, user_id: str):
        """
        Removes a user's session from the session manager and clears resume state.
        """
        # Clear the resume session name to prevent automatic resumption
        self.resume_session_name = None

        # Call parent reset logic
        return super().reset_user_session(user_id)

    def handle_user_message(
        self, user_id: str, text: str, user_email: str = None
    ) -> str:
        """
        Handles an incoming message with LangGraph-specific termination handling.
        """
        # Call parent logic first
        agent_response = super().handle_user_message(user_id, text, user_email)

        # LangGraph-specific termination handling for ResponsesAgentManager
        if user_id in self.user_sessions:
            current_session = self.user_sessions[user_id]

            # Check if this is a LangGraph termination response and clean it up
            if self._is_specialist_session(current_session):
                # Check the full response for termination markers
                response_lower = agent_response.lower()
                if (
                    "conversation completed" in response_lower
                    or "starting new conversation" in response_lower
                ):
                    # Mark this session for reset after displaying the response
                    current_session["_pending_reset"] = True

                    # Clean up the response - remove termination markers
                    if "\n" in agent_response:
                        lines = agent_response.strip().split("\n")
                        clean_lines = []
                        for line in lines:
                            line_lower = line.lower()
                            if not (
                                "conversation completed" in line_lower
                                or "starting new conversation" in line_lower
                            ):
                                clean_lines.append(line)
                        if clean_lines:
                            return "\n".join(clean_lines).strip()

                    # If no clean lines or no newlines, return original
                    return agent_response.strip()

        return agent_response

    def get_current_thread_id(self, user_id: str) -> str:
        """Get the current thread ID for a user session."""
        if user_id not in self.user_sessions:
            return None

        session_info = self.user_sessions[user_id]
        conversation_session = session_info.get("conversation_session")
        if conversation_session:
            return conversation_session.thread_id
        return None


def create_session_manager_responses(session_name=None):
    """
    Factory function to initialize a ResponsesAgentManager,
    and return a fully configured SessionManagerResponses instance.

    Args:
        session_name: Optional session name for resuming existing conversations
    """
    agent_manager = ResponsesAgentManager()
    session_manager = SessionManagerResponses(
        agent_manager=agent_manager, session_name=session_name
    )

    return session_manager
