"""Session Management for Agent Service.

This module provides session management for both LlamaStack Agent API and Responses API.

Architecture:
- BaseSessionManager: Core database operations for Request Manager sessions
- ResponsesSessionManager: Extends base with LangGraph conversation management

Usage:
- LlamaStack Agent API: Use BaseSessionManager for database operations only
- Responses API: Use ResponsesSessionManager for full conversation management
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from shared_models import configure_logging, get_enum_value
from shared_models.models import RequestSession, SessionStatus
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import SessionCreate, SessionResponse

logger = configure_logging("agent-service")

# Configure logging to suppress verbose output
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)
logging.getLogger("asset_manager").setLevel(logging.WARNING)


def get_session_token_context(session_id: str | None) -> str:
    """Generate session-specific token context for consistent token counting.

    Args:
        session_id: The Request Manager session ID (can be None for fallback)

    Returns:
        Session-specific token context string (e.g., "session_123" or "fallback_session")
    """
    if session_id is None:
        return "fallback_session"
    return f"session_{session_id}"


class BaseSessionManager:
    """Base session management for LlamaStack Agent API.

    This class handles core database operations for Request Manager sessions:
    - Session lifecycle (create, update, get)
    - User context and integration metadata storage
    - Current agent assignment tracking
    - Request count tracking

    Used by LlamaStack Agent API for database-only operations.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize base session manager for database operations only."""
        self.db_session = db_session

    # =============================================================================
    # LLAMASTACK AGENT API - DATABASE OPERATIONS
    # =============================================================================
    async def create_session(self, session_data: SessionCreate) -> SessionResponse:
        """Create a new Request Manager session in the database."""
        session = RequestSession(
            session_id=str(uuid.uuid4()),
            user_id=session_data.user_id,
            integration_type=get_enum_value(session_data.integration_type),
            channel_id=session_data.channel_id,
            thread_id=session_data.thread_id,
            external_session_id=session_data.external_session_id,
            integration_metadata=session_data.integration_metadata,
            user_context=session_data.user_context,
            status=SessionStatus.ACTIVE.value,
        )

        self.db_session.add(session)
        await self.db_session.commit()
        await self.db_session.refresh(session)

        return SessionResponse.model_validate(session)

    async def get_session(self, session_id: str) -> Optional[SessionResponse]:
        """Get Request Manager session by ID from database."""
        stmt = select(RequestSession).where(RequestSession.session_id == session_id)
        result = await self.db_session.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            return SessionResponse.model_validate(session)
        return None

    async def update_session(
        self,
        session_id: str,
        agent_id: Optional[str] = None,
        conversation_thread_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        conversation_context: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[SessionResponse]:
        """Update Request Manager session information in database."""
        update_data: Dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc),
            "last_request_at": datetime.now(timezone.utc),
        }

        if agent_id is not None:
            update_data["current_agent_id"] = agent_id
        if conversation_thread_id is not None:
            update_data["conversation_thread_id"] = conversation_thread_id
        if status is not None:
            update_data["status"] = status
        if conversation_context is not None:
            update_data["conversation_context"] = conversation_context
        if user_context is not None:
            update_data["user_context"] = user_context

        stmt = (
            update(RequestSession)
            .where(RequestSession.session_id == session_id)
            .values(**update_data)
            .returning(RequestSession)
        )

        result = await self.db_session.execute(stmt)
        await self.db_session.commit()
        updated_session = result.scalar_one_or_none()

        if updated_session:
            return SessionResponse.from_orm(updated_session)
        return None

    async def increment_request_count(self, session_id: str, request_id: str) -> None:
        """Increment the request count for a session."""
        stmt = (
            update(RequestSession)
            .where(RequestSession.session_id == session_id)
            .values(
                total_requests=RequestSession.total_requests + 1,
                last_request_id=request_id,
                last_request_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

        await self.db_session.execute(stmt)
        await self.db_session.commit()


class ResponsesSessionManager(BaseSessionManager):
    """Extended session management for Responses API.

    This class extends BaseSessionManager with LangGraph conversation management:
    - Stateful conversation handling
    - Agent routing and specialist agent management
    - Session resumption and metadata persistence
    - Task completion detection and auto-routing

    Used by Responses API for full conversation state management.
    """

    ROUTING_AGENT_NAME = "routing-agent"

    def __init__(
        self,
        db_session: AsyncSession,
        user_id: str,
        user_email: Optional[str] = None,
    ) -> None:
        """Initialize responses session manager with conversation state."""
        super().__init__(db_session)
        self.user_id = user_id
        self.user_email = user_email

        # Conversation state for responses mode
        self.current_session: dict[str, Any] | None = None
        self.current_agent_name: str | None = None
        self.conversation_session: Any | None = None
        self.agent_manager: Any | None = None
        self.agents: list[Any] = []
        self.request_manager_session_id: str | None = None

        self._initialize_conversation_state()

    def _initialize_conversation_state(self) -> None:
        """Initialize conversation state for responses mode."""
        try:
            from .langgraph import ResponsesAgentManager

            self.agent_manager = ResponsesAgentManager()
            assert (
                self.agent_manager is not None
            )  # ResponsesAgentManager() never returns None
            self.agents = list(self.agent_manager.agents_dict.keys())
            logger.info(f"Loaded agents for responses mode - agents: {self.agents}")
        except ImportError as e:
            logger.warning(f"LangGraph components not available: {e}")
            self.agent_manager = None
            self.agents = []
        except Exception as e:
            logger.error(f"Failed to initialize ResponsesAgentManager: {e}")
            self.agent_manager = None
            self.agents = []

    # =============================================================================
    # RESPONSES API - CONVERSATION MANAGEMENT
    # =============================================================================
    async def handle_responses_message(
        self,
        text: str,
        request_manager_session_id: Optional[str] = None,
        session_name: Optional[str] = None,
    ) -> str:
        """Handle a message in responses mode with full conversation management."""
        if not self.user_id:
            logger.error(f"Responses mode not available - user_id: {self.user_id}")
            return "Error: Responses mode not available"

        if not self.agent_manager:
            logger.error("Agent manager not initialized")
            return "Error: Agent manager not initialized"

        # Store the request manager session ID for database updates
        if request_manager_session_id:
            self.request_manager_session_id = request_manager_session_id

        logger.debug(
            f"Handling responses message - user_id: {self.user_id}, message_preview: {text[:100]}, request_manager_session_id: {request_manager_session_id}, session_name: {session_name}, has_current_session: {bool(self.current_session)}, current_agent: {self.current_agent_name}"
        )

        try:
            # Check if we need to create or resume a session
            if not self.current_session:
                # Try to resume existing session from database
                if request_manager_session_id:
                    logger.debug(
                        f"Attempting to resume existing session - request_manager_session_id: {request_manager_session_id}, user_id: {self.user_id}"
                    )
                    session_resumed = await self._resume_session_from_database(
                        request_manager_session_id
                    )
                    if session_resumed:
                        logger.info(
                            f"Resumed existing session - request_manager_session_id: {request_manager_session_id}, thread_id: {self.conversation_session.thread_id if self.conversation_session else None}, current_agent: {self.current_agent_name}"
                        )
                    else:
                        logger.debug(
                            f"No existing session found, creating new session - request_manager_session_id: {request_manager_session_id}, user_id: {self.user_id}"
                        )

                # If session not resumed, create a new one
                if not self.current_session:
                    logger.debug(
                        f"Creating initial session for responses mode - user_id: {self.user_id}, session_name: {session_name}"
                    )
                    success = await self._create_initial_session(session_name)
                    if not success:
                        logger.error(
                            f"Failed to create initial session - user_id: {self.user_id}, session_name: {session_name}"
                        )
                        return "Error: Failed to create session"

            # Check if we need to return to routing agent after task completion
            if self.current_session and self.current_session.get("_pending_reset"):
                logger.info(
                    f"Specialist task complete, returning to routing agent - user_id: {self.user_id}, current_agent: {self.current_agent_name}"
                )
                await self._reset_conversation_state()
                return await self.handle_responses_message("hi")

            # Send message to current session
            logger.debug(
                f"Sending message to LangGraph session - user_id: {self.user_id}, current_agent: {self.current_agent_name}, thread_id: {self.conversation_session.thread_id if self.conversation_session else None}"
            )

            token_context = get_session_token_context(self.request_manager_session_id)
            if self.conversation_session is None:
                logger.error("Conversation session not initialized")
                return "Error: Conversation session not initialized"

            response = self.conversation_session.send_message(
                text,
                token_context=token_context,
            )
            processed_response = self._process_agent_response(response)

            # Handle routing logic
            logger.debug(
                "Handling routing logic",
                user_id=self.user_id,
                current_agent=self.current_agent_name,
                response_preview=processed_response[:100],
            )

            processed_response = await self._handle_routing(processed_response, text)

            logger.info(
                f"Responses message processed successfully - user_id: {self.user_id}, current_agent: {self.current_agent_name}, response_length: {len(processed_response)}"
            )

            return processed_response

        except Exception as e:
            logger.error(
                f"Error handling responses message - error: {str(e)}, error_type: {type(e).__name__}, user_id: {self.user_id}, current_agent: {self.current_agent_name}, message_preview: {text[:100]}",
                exc_info=e,
            )
            return f"Error: {str(e)}"

    async def _create_initial_session(self, session_name: Optional[str] = None) -> bool:
        """Create an initial session for responses mode."""
        try:
            logger.debug(
                f"Creating initial session for responses mode - user_id: {self.user_id}, session_name: {session_name}"
            )

            # Get routing agent
            if self.agent_manager is None:
                logger.error(
                    "Agent manager not initialized. Cannot create initial session."
                )
                return False

            routing_agent = self.agent_manager.get_agent(self.ROUTING_AGENT_NAME)
            if not routing_agent:
                logger.error(
                    f"Core routing agent not available - user_id: {self.user_id}, routing_agent_name: {self.ROUTING_AGENT_NAME}, available_agents: {list(self.agent_manager.agents_dict.keys()) if self.agent_manager else []}"
                )
                return False

            # Debug: Check routing agent configuration
            lg_config = routing_agent.config.get("lg_state_machine_config")
            logger.info(
                f"Routing agent configuration - lg_state_machine_config: {lg_config}"
            )

            # Generate session name and create session
            session_name = session_name or self._generate_session_name()
            logger.debug(
                f"Creating LangGraph session - user_id: {self.user_id}, session_name: {session_name}, routing_agent: {self.ROUTING_AGENT_NAME}"
            )

            session = self._create_session_for_agent(
                routing_agent,
                self.ROUTING_AGENT_NAME,
                session_name=session_name,
            )

            # Debug: Check StateMachine configuration
            logger.info(
                f"StateMachine configuration - config_path: {session.config_path}, initial_state: {session.state_machine.config.get('settings', {}).get('initial_state')}"
            )

            # Set up the new session
            self.conversation_session = session
            self.current_agent_name = self.ROUTING_AGENT_NAME
            self.current_session = self._build_session_data(
                routing_agent, self.ROUTING_AGENT_NAME, session, session_name
            )

            logger.debug(
                f"Session created successfully - user_id: {self.user_id}, session_name: {session_name}, thread_id: {session.thread_id}, current_agent: {self.current_agent_name}"
            )

            # Update database with current agent
            logger.debug(
                f"Updating database session state - user_id: {self.user_id}, agent_name: {self.ROUTING_AGENT_NAME}, thread_id: {session.thread_id}"
            )

            await self._update_database_session_state(
                self.ROUTING_AGENT_NAME,
                session.thread_id,
                self.request_manager_session_id,
            )

            logger.info(
                f"Initial session created and database updated - user_id: {self.user_id}, session_name: {session_name}, thread_id: {session.thread_id}, current_agent: {self.current_agent_name}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to create new session - error: {str(e)}, error_type: {type(e).__name__}, user_id: {self.user_id}, session_name: {session_name}",
                exc_info=e,
            )
            return False

    async def _resume_session_from_database(
        self, request_manager_session_id: str
    ) -> bool:
        """Resume an existing session from the database."""
        try:
            # Load session from database
            db_session = await self.get_session(request_manager_session_id)
            if not db_session:
                logger.debug(
                    f"No existing session found in database - request_manager_session_id: {request_manager_session_id}, user_id: {self.user_id}"
                )
                return False

            # Extract session metadata
            current_agent_id = db_session.current_agent_id
            conversation_thread_id = db_session.conversation_thread_id
            conversation_context = db_session.conversation_context or {}

            if not conversation_thread_id or not current_agent_id:
                logger.debug(
                    f"Session found but missing required fields - request_manager_session_id: {request_manager_session_id}, current_agent_id: {current_agent_id}, conversation_thread_id: {conversation_thread_id}"
                )
                return False

            logger.info(
                f"Resuming session from database - request_manager_session_id: {request_manager_session_id}, current_agent_id: {current_agent_id}, conversation_thread_id: {conversation_thread_id}"
            )

            # Get the agent
            if self.agent_manager is None:
                logger.error("Agent manager not initialized. Cannot resume session.")
                return False

            agent = self.agent_manager.get_agent(current_agent_id)
            if not agent:
                logger.error(
                    f"Agent not found for resumption - agent_id: {current_agent_id}, available_agents: {list(self.agent_manager.agents_dict.keys()) if self.agent_manager else []}"
                )
                return False

            # Create session for agent with existing thread_id
            session_name = conversation_context.get(
                "session_name", f"session-{self.user_id}"
            )
            session = self._create_session_for_agent(
                agent,
                current_agent_id,
                session_name=session_name,
                resume_thread_id=conversation_thread_id,
            )

            # Set up the resumed session
            self.conversation_session = session
            self.current_agent_name = current_agent_id
            self.current_session = self._build_session_data(
                agent, current_agent_id, session, session_name
            )

            logger.info(
                f"Session resumed successfully - request_manager_session_id: {request_manager_session_id}, current_agent: {self.current_agent_name}, thread_id: {conversation_thread_id}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to resume session - error: {str(e)}, error_type: {type(e).__name__}, request_manager_session_id: {request_manager_session_id}, user_id: {self.user_id}",
                exc_info=e,
            )
            return False

    def _create_session_for_agent(
        self,
        agent: Any,
        agent_name: str,
        session_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create a new session for the given agent."""
        from .langgraph import ConversationSession

        # Extract parameters from kwargs
        resume_thread_id = kwargs.get("resume_thread_id")
        # Use user_id as authoritative_user_id for employee lookup, fallback to user_email if available
        authoritative_user_id = kwargs.get(
            "authoritative_user_id", self.user_id or self.user_email
        )

        # Use provided thread_id for resumption or generate a new one
        if resume_thread_id:
            session_thread_id = resume_thread_id
        else:
            session_thread_id = str(uuid.uuid4())

        checkpoint_db_path = f"/tmp/conversation_checkpoints_{self.user_id}.db"

        return ConversationSession(
            agent,
            session_thread_id,
            checkpoint_db_path,
            authoritative_user_id=authoritative_user_id,
        )

    def _build_session_data(
        self, agent: Any, agent_name: str, session: Any, session_name: str
    ) -> dict[str, Any]:
        """Build session data dictionary for updating current session."""
        return {
            "agent_name": agent_name,
            "conversation_session": session,
            "session_name": session_name,
        }

    def _generate_session_name(self, agent_name: str | None = None) -> str:
        """Generate a unique session name."""
        unique_id = str(uuid.uuid4())[:8]
        if agent_name:
            return f"session-{self.user_id}-{agent_name}-{unique_id}"
        else:
            return f"session-{self.user_id}-{unique_id}"

    def _is_specialist_session(self) -> bool:
        """Check if current session is with a specialist agent."""
        return self.current_agent_name != self.ROUTING_AGENT_NAME

    def _is_routing_session(self) -> bool:
        """Check if current session is with the routing agent."""
        return self.current_agent_name == self.ROUTING_AGENT_NAME

    def _process_agent_response(
        self, response: str, fallback_message: str = "No response received from agent"
    ) -> str:
        """Process and normalize agent response."""
        if response:
            return response.strip()
        return fallback_message

    async def _handle_routing(self, processed_response: str, text: str) -> str:
        """Handle agent routing logic using unified routing detection."""

        # Debug logging with structured format
        logger.debug(
            "Responses API routing check",
            user_id=self.user_id,
            response_preview=processed_response[:100],
            available_agents=self.agents,
            current_agent=self.current_agent_name,
            is_routing_session=self._is_routing_session(),
        )

        # Debug LangGraph state machine state
        if self.conversation_session:
            try:
                current_state = self.conversation_session.app.get_state(
                    self.conversation_session.thread_config
                )
                current_values = current_state.values
                current_state_name = current_values.get("current_state", "unknown")
                routing_decision = current_values.get("routing_decision")
                user_intent = current_values.get("user_intent")
                logger.info(
                    f"LangGraph state machine state - current_state: {current_state_name}, routing_decision: {routing_decision}, user_intent: {user_intent}, thread_id: {self.conversation_session.thread_id}"
                )
            except Exception as e:
                logger.warning(
                    "Could not get LangGraph state",
                    error=str(e),
                    user_id=self.user_id,
                )
        else:
            logger.debug(
                "LangGraph state machine state: no conversation session",
                user_id=self.user_id,
            )

        # Log the full response and available agents
        logger.info(
            f"Routing analysis - full_response: '{processed_response}', available_agents: {self.agents}, current_agent: {self.current_agent_name}"
        )

        # Use StateMachine routing_decision field instead of parsing messages
        routed_agent = None

        # Check conversation state for routing decision from StateMachine
        if self.conversation_session:
            try:
                current_state = self.conversation_session.app.get_state(
                    self.conversation_session.thread_config
                )
                current_values = current_state.values
                routing_decision = current_values.get("routing_decision")
                user_intent = current_values.get("user_intent")
                current_state_name = current_values.get("current_state")

                logger.info(
                    f"StateMachine state check - current_state: {current_state_name}, routing_decision: {routing_decision}, user_intent: {user_intent}"
                )

                if routing_decision and routing_decision in self.agents:
                    routed_agent = routing_decision
                    logger.info(
                        f"Found routing decision from StateMachine - agent: {routed_agent}"
                    )
                else:
                    logger.info(
                        f"No valid routing decision in StateMachine state - routing_decision: {routing_decision}, available_agents: {self.agents}"
                    )
            except Exception as e:
                logger.warning(
                    "Could not get routing decision from StateMachine state",
                    error=str(e),
                    user_id=self.user_id,
                )

        # Fallback: Check for direct agent name in response (for backward compatibility)
        if not routed_agent:
            signal = processed_response.strip().lower()

            # Check if response contains exact agent name
            for agent_name in self.agents:
                if agent_name.lower() in signal:
                    routed_agent = agent_name
                    logger.info(
                        f"Found agent name in response (fallback) - agent: {agent_name}, signal: {signal}"
                    )
                    break

        logger.debug(f"Routing detection result - routed_agent: {routed_agent}")

        if routed_agent:
            logger.info(
                "Responses mode routing detected",
                user_id=self.user_id,
                routing_response_preview=processed_response[:100],
                target_agent_name=routed_agent,
                current_agent=self.current_agent_name,
            )

            # Handle task completion - return to router
            if (
                routed_agent == self.ROUTING_AGENT_NAME
                and self._is_specialist_session()
            ):
                logger.info(
                    "Specialist task complete, returning to routing agent",
                    user_id=self.user_id,
                    current_agent=self.current_agent_name,
                )
                await self._reset_conversation_state()
                return await self.handle_responses_message("hi")

            # Handle routing to specialist agents
            if routed_agent != self.ROUTING_AGENT_NAME and self._is_routing_session():
                logger.info(
                    "Routing to specialist agent",
                    user_id=self.user_id,
                    target_agent=routed_agent,
                    current_agent=self.current_agent_name,
                    message_preview=text[:100],
                )
                return await self._route_to_specialist(routed_agent, text)

        # LangGraph-specific termination handling for specialist sessions
        if self._is_specialist_session() and self.current_session:
            response_lower = processed_response.lower()
            if (
                "conversation completed" in response_lower
                or "starting new conversation" in response_lower
            ):
                logger.info(
                    "Specialist session termination detected",
                    user_id=self.user_id,
                    current_agent=self.current_agent_name,
                    termination_phrases=[
                        phrase
                        for phrase in [
                            "conversation completed",
                            "starting new conversation",
                        ]
                        if phrase in response_lower
                    ],
                )

                self.current_session["_pending_reset"] = True

                # Clean up the response - remove termination markers
                if "\n" in processed_response:
                    lines = processed_response.strip().split("\n")
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

        return processed_response

    async def _route_to_specialist(self, agent_name: str, text: str) -> str:
        """Route the conversation to a specialist agent."""
        try:
            logger.debug(
                "Routing to specialist agent",
                user_id=self.user_id,
                target_agent=agent_name,
                current_agent=self.current_agent_name,
                message_preview=text[:100],
            )

            # Get the specialist agent
            if self.agent_manager is None:
                logger.error(
                    "Agent manager not initialized. Cannot route to specialist."
                )
                return "Error: Agent manager not initialized."

            agent = self.agent_manager.get_agent(agent_name)
            if not agent:
                logger.error(
                    "Specialist agent not found",
                    user_id=self.user_id,
                    target_agent=agent_name,
                    available_agents=(
                        list(self.agent_manager.agents_dict.keys())
                        if self.agent_manager
                        else []
                    ),
                )
                return f"Error: Agent '{agent_name}' not found"

            # Generate session name
            session_name = self._generate_session_name(agent_name)
            logger.debug(
                "Creating specialist agent session",
                user_id=self.user_id,
                target_agent=agent_name,
                session_name=session_name,
            )

            # Create session for the specialist agent
            session = self._create_session_for_agent(
                agent,
                agent_name,
                session_name=session_name,
            )

            # Update current session
            self.conversation_session = session
            self.current_agent_name = agent_name
            self.current_session = self._build_session_data(
                agent, agent_name, session, session_name
            )

            logger.debug(
                "Specialist agent session created",
                user_id=self.user_id,
                target_agent=agent_name,
                session_name=session_name,
                thread_id=session.thread_id,
            )

            # Update database
            logger.debug(
                "Updating database with specialist agent",
                user_id=self.user_id,
                target_agent=agent_name,
                thread_id=session.thread_id,
            )

            await self._update_database_session_state(
                agent_name, session.thread_id, self.request_manager_session_id
            )

            # Send the message to the new agent
            logger.debug(
                "Sending message to specialist agent",
                user_id=self.user_id,
                target_agent=agent_name,
                message_preview=text[:100],
            )

            token_context = get_session_token_context(self.request_manager_session_id)
            response = session.send_message(
                text,
                token_context=token_context,
            )

            logger.info(
                "Successfully routed to specialist agent",
                user_id=self.user_id,
                target_agent=agent_name,
                thread_id=session.thread_id,
                response_length=len(response),
            )

            return self._process_agent_response(response)

        except Exception as e:
            logger.error(
                "Failed to route to specialist agent",
                error=str(e),
                error_type=type(e).__name__,
                user_id=self.user_id,
                target_agent=agent_name,
                current_agent=self.current_agent_name,
            )
            return f"Error: {str(e)}"

    async def _update_database_session_state(
        self, agent_name: str, thread_id: str, session_id: str | None = None
    ) -> None:
        """Update the database with current session state."""
        try:
            logger.debug(
                "Updating database session state",
                user_id=self.user_id,
                agent_name=agent_name,
                thread_id=thread_id,
                session_id=session_id,
            )

            # Find the specific session if session_id provided, otherwise find user's most recent active session
            if session_id:
                stmt = select(RequestSession).where(
                    RequestSession.session_id == session_id
                )
            else:
                stmt = (
                    select(RequestSession)
                    .where(
                        RequestSession.user_id == self.user_id,
                        RequestSession.status == SessionStatus.ACTIVE.value,
                    )
                    .order_by(RequestSession.last_request_at.desc())
                )

            result = await self.db_session.execute(stmt)
            session = result.scalar_one_or_none()

            if session:
                logger.debug(
                    "Found active session for user",
                    user_id=self.user_id,
                    session_id=session.session_id,
                    current_agent_id=session.current_agent_id,
                )

                # Update the session with current agent and thread
                conversation_context = {
                    "agent_name": agent_name,
                    "session_type": "responses_api",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }

                update_stmt = (
                    update(RequestSession)
                    .where(RequestSession.session_id == session.session_id)
                    .values(
                        current_agent_id=agent_name,
                        conversation_thread_id=thread_id,
                        conversation_context=conversation_context,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await self.db_session.execute(update_stmt)
                await self.db_session.commit()

                logger.info(
                    f"Database session state updated successfully - user_id: {self.user_id}, session_id: {session.session_id}, agent_name: {agent_name}, thread_id: {thread_id}"
                )
            else:
                logger.warning(
                    f"No active session found for user - user_id: {self.user_id}"
                )

        except Exception as e:
            logger.error(
                f"Failed to update database session state - error: {str(e)}, error_type: {type(e).__name__}, user_id: {self.user_id}, agent_name: {agent_name}, thread_id: {thread_id}",
                exc_info=e,
            )

    async def _reset_conversation_state(self) -> None:
        """Reset the conversation state."""
        try:
            logger.debug(
                "Resetting conversation state",
                user_id=self.user_id,
                current_agent=self.current_agent_name,
                has_conversation_session=bool(self.conversation_session),
            )

            # Clean up current session
            if self.conversation_session:
                logger.debug(
                    "Closing conversation session",
                    user_id=self.user_id,
                    thread_id=self.conversation_session.thread_id,
                )
                self.conversation_session.close()

            # Reset state
            self.current_session = None
            self.current_agent_name = None
            self.conversation_session = None

            logger.debug(
                "Resetting internal state",
                user_id=self.user_id,
            )

            # Update database to clear session state
            logger.debug(
                "Updating database to clear session state",
                user_id=self.user_id,
            )

            stmt = (
                update(RequestSession)
                .where(
                    RequestSession.user_id == self.user_id,
                    RequestSession.status == SessionStatus.ACTIVE.value,
                )
                .values(
                    current_agent_id=None,
                    conversation_thread_id=None,
                    status=SessionStatus.INACTIVE.value,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self.db_session.execute(stmt)
            await self.db_session.commit()

            logger.info(
                "Conversation state reset successfully",
                user_id=self.user_id,
            )

        except Exception as e:
            logger.error(
                "Failed to reset conversation state",
                error=str(e),
                error_type=type(e).__name__,
                user_id=self.user_id,
            )

    def get_current_thread_id(self) -> Optional[str]:
        """Get the current thread ID for the user session."""
        if self.conversation_session:
            return str(self.conversation_session.thread_id)
        return None

    def get_current_agent_name(self) -> Optional[str]:
        """Get the current agent name for the user session."""
        return self.current_agent_name

    async def close(self) -> None:
        """Close the session manager and clean up resources."""
        if self.conversation_session:
            self.conversation_session.close()
        self.current_session = None
        self.current_agent_name = None
        self.conversation_session = None
