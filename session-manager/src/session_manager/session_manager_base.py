import json
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionManagerBase(ABC):
    """
    Base class for session managers with common functionality.
    """

    ROUTING_AGENT_NAME = "routing-agent"

    def __init__(self, agent_manager):
        """
        Initializes the SessionManagerBase.

        Args:
            agent_manager: An agent manager instance (AgentManager or ResponsesAgentManager).
        """
        self.agent_manager = agent_manager
        self.agents = agent_manager.agents()
        self.user_sessions = {}

        # Optional session metadata persistence
        self.metadata_file = None  # Subclasses can set this to enable persistence
        self.session_metadata = {}

    def _generate_session_name(self, user_id: str, agent_name: str = None) -> str:
        """Generate a unique session name"""
        unique_id = str(uuid.uuid4())[:8]  # First 8 characters of UUID

        if agent_name:
            return f"session-{user_id}-{agent_name}-{unique_id}"
        else:
            return f"session-{user_id}-{unique_id}"

    def _process_agent_response(
        self, response: str, fallback_message: str = "No response received from agent"
    ) -> str:
        """Process and normalize agent response."""
        if response:
            return response.strip()
        return fallback_message

    def _handle_agent_error(self, error: Exception) -> str:
        """Handle agent communication errors."""
        logger.error(f"Error in send_message_to_agent: {error}")
        return f"Error: {str(error)}"

    @abstractmethod
    def send_message_to_agent(
        self, agent_id: str, session_id: str, message: str
    ) -> str:
        """Send a message to an agent and return the response"""
        pass

    @abstractmethod
    def _build_initial_session_data(
        self, routing_agent, session, session_name: str, user_email: str
    ) -> dict:
        """Build initial session data structure for a new user."""
        pass

    def _create_initial_session(self, user_id: str, user_email: str = None):
        """Create an initial session for a new user"""
        # Get routing agent
        routing_agent = self._get_agent_for_routing(self.ROUTING_AGENT_NAME)
        if not routing_agent:
            return "Error: Core routing agent not available."

        # Generate session name and create session
        session_name = self._generate_session_name(user_id)
        session = self._create_session_for_agent(
            routing_agent, self.ROUTING_AGENT_NAME, user_id, session_name=session_name
        )

        # Store session metadata for future resumption (if metadata storage is enabled)
        if hasattr(session, "thread_id") and self.metadata_file:
            self._store_session_metadata(
                session_name, session.thread_id, self.ROUTING_AGENT_NAME
            )

        # Build session data and store
        session_data = self._build_initial_session_data(
            routing_agent, session, session_name, user_email
        )
        self.user_sessions[user_id] = session_data

    @abstractmethod
    def _get_agent_for_routing(self, agent_name: str):
        """Get the agent object/identifier for routing."""
        pass

    @abstractmethod
    def _create_session_for_agent(
        self,
        agent,
        agent_name: str,
        user_id: str,
        session_name: str = None,
        resume_thread_id: str = None,
    ):
        """Create a new session for the given agent."""
        pass

    @abstractmethod
    def _build_session_data(
        self, agent, agent_name: str, session, session_name: str
    ) -> dict:
        """Build session data dictionary for updating current session."""
        pass

    @abstractmethod
    def _update_session_fields(self, current_session, session_data):
        """Update the current session fields with new session data."""
        pass

    def _create_specialist_session(
        self, agent_name: str, user_id: str, resume_thread_id: str = None
    ) -> tuple:
        """Create a new session for a specialist agent."""
        # Get the specialist agent
        agent = self._get_agent_for_routing(agent_name)
        if not agent:
            return None, f"Error: Agent '{agent_name}' not found"

        # Generate session name
        session_name = self._generate_session_name(user_id, agent_name)

        # Create session using implementation-specific method
        session = self._create_session_for_agent(
            agent,
            agent_name,
            user_id,
            session_name=session_name,
            resume_thread_id=resume_thread_id,
        )

        # Store session metadata for future resumption (if metadata storage is enabled)
        if hasattr(session, "thread_id") and self.metadata_file:
            self._store_session_metadata(session_name, session.thread_id, agent_name)

        # Build session data using implementation-specific structure
        session_data = self._build_session_data(
            agent, agent_name, session, session_name
        )
        return session_data, None

    def _update_session_for_specialist(
        self, current_session, agent_name: str, session_data
    ):
        """Update the current session to use the specialist agent session."""
        self._update_session_fields(current_session, session_data)

    def _route_to_specialist(self, user_id, agent_name, text, current_session):
        """Routes the conversation to a specialist agent."""
        logger.debug(f"Routing to agent: {agent_name}")

        # Get resume_thread_id from current session if available
        resume_thread_id = current_session.get("resume_thread_id")

        # Create a new session for the specialist agent
        session_data, error = self._create_specialist_session(
            agent_name, user_id, resume_thread_id
        )
        if error:
            return error

        # Update the current session to the new specialist agent
        self._update_session_for_specialist(current_session, agent_name, session_data)

        # Send the message to the new agent
        agent_response = self._send_message_to_current_session(current_session, text)
        return agent_response

    def handle_user_message(
        self, user_id: str, text: str, user_email: str = None
    ) -> str:
        """
        Handles an incoming message, manages sessions and history, and returns a response.
        """
        if user_id not in self.user_sessions:
            result = self._create_initial_session(user_id, user_email)
            if isinstance(result, str):  # Error message
                return result
            logger.debug(f"New session for user {user_id} ({user_email})")

        current_session = self.user_sessions[user_id]

        # Check if we need to return to routing agent after task completion
        if current_session.get("_pending_reset"):
            logger.debug(
                f"Specialist task complete. Returning user {user_id} to the routing agent."
            )
            self.reset_user_session(user_id)
            return self.handle_user_message(user_id, "hi", user_email)

        agent_response = self._send_message_to_current_session(current_session, text)

        # Extract routing signal, handling both single responses and multi-line responses
        signal = agent_response.strip().lower()

        # If response contains multiple lines, look for agent names in the response
        if "\n" in signal:
            lines = signal.split("\n")
            # Look for lines that match agent names
            for line in lines:
                line = line.strip()
                if line in self.agents:
                    signal = line
                    break
            else:
                # If no agent name found in lines, use first line (fallback)
                signal = lines[0].strip()

        # If no agent found yet, check if any agent name appears at the end of the response
        if signal not in self.agents:
            for agent_name in self.agents:
                if signal.endswith(agent_name):
                    signal = agent_name
                    break

        # Handle task completion - return to router
        if (signal == "task_complete_return_to_router") and self._is_specialist_session(
            current_session
        ):
            logger.debug(
                f"Specialist task complete. Returning user {user_id} to the routing agent."
            )
            self.reset_user_session(user_id)
            return self.handle_user_message(user_id, "hi", user_email)

        # Handle routing to specialist agents
        if (
            signal in self.agents
            and signal != self.ROUTING_AGENT_NAME
            and self._is_routing_session(current_session)
        ):
            return self._route_to_specialist(user_id, signal, text, current_session)

        return agent_response

    @abstractmethod
    def _send_message_to_current_session(self, current_session, text: str) -> str:
        """Send message to the current session and return response"""
        pass

    def _get_session_agent_identifier(self, current_session) -> str:
        """Get the agent identifier from the current session"""
        return current_session["agent_name"]

    def _is_specialist_session(self, current_session) -> bool:
        """Check if current session is with a specialist agent"""
        current_agent_name = self._get_session_agent_identifier(current_session)
        return current_agent_name != self.ROUTING_AGENT_NAME

    def _is_routing_session(self, current_session) -> bool:
        """Check if current session is with the routing agent"""
        current_agent_name = self._get_session_agent_identifier(current_session)
        return current_agent_name == self.ROUTING_AGENT_NAME

    @abstractmethod
    def _cleanup_session(self, session_info):
        """Clean up session-specific resources"""
        pass

    def reset_user_session(self, user_id: str):
        """
        Removes a user's session from the session manager.
        """
        if user_id in self.user_sessions:
            session_info = self.user_sessions[user_id]
            self._cleanup_session(session_info)

            del self.user_sessions[user_id]
            logger.debug(f"Session for user {user_id} has been reset.")
            return True
        return False

    def get_current_session_name(self, user_id: str) -> str:
        """Get the current session name for a user session."""
        if user_id not in self.user_sessions:
            return None

        session_info = self.user_sessions[user_id]
        return session_info.get("session_name")

    def _load_metadata(self) -> dict:
        """Load session metadata from persistent storage (if enabled)."""
        if not self.metadata_file:
            return {}

        try:
            metadata_path = Path(self.metadata_file)
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                    logger.debug(
                        f"Loaded {len(data)} metadata entries from {self.metadata_file}"
                    )
                    return data
        except Exception as e:
            logger.error(f"Failed to load metadata from {self.metadata_file}: {e}")
        return {}

    def _save_metadata(self, metadata: dict):
        """Save session metadata to persistent storage (if enabled)."""
        if not self.metadata_file:
            return

        try:
            metadata_path = Path(self.metadata_file)
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata to {self.metadata_file}: {e}")

    def _store_metadata(self, key: str, value: any):
        """Store metadata for a session (generic method for subclasses to use)."""
        if not self.metadata_file:
            return

        self.session_metadata[key] = value
        self._save_metadata(self.session_metadata)

    def _get_metadata(self, key: str, default=None):
        """Get metadata for a session (generic method for subclasses to use)."""
        return self.session_metadata.get(key, default)

    def _initialize_metadata(self):
        """Initialize metadata storage (call this in subclass __init__ if needed)."""
        if self.metadata_file:
            self.session_metadata = self._load_metadata()

    def _store_session_metadata(
        self, session_name: str, thread_id: str, agent_name: str
    ):
        """Store session metadata for future resumption (generic implementation)."""
        metadata_value = [thread_id, agent_name]  # Use list for JSON serialization
        logger.debug(
            f"Stored session {session_name} -> thread {thread_id}, agent {agent_name}"
        )
        self._store_metadata(session_name, metadata_value)

    def _get_session_metadata(self, session_name: str) -> tuple:
        """Get session metadata (thread_id, agent_name) for a session name."""
        data = self._get_metadata(session_name, [None, None])
        return tuple(data)
