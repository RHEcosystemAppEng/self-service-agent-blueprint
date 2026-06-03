"""Session Management for Agent Service."""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from shared_models import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    BaseSessionManager,
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    configure_logging,
    effective_entry_agent_id,
    effective_router_agent_id,
    get_enum_value,
    policy_from_integration_metadata,
    policy_needs_ticket_context,
    resolve_channel_behavior_sync,
)
from shared_models.models import RequestSession, SessionStatus
from shared_models.user_utils import is_uuid
from shared_models.utils import json_value_as_dict
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

logger = configure_logging("agent-service")

# Configure logging to suppress verbose output
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)


def _default_agent_id_resolved() -> str:
    """``DEFAULT_AGENT_ID`` — LangGraph router identity (see ``ROUTING_AGENT_NAME``)."""
    return os.getenv("DEFAULT_AGENT_ID", "routing-agent").strip() or "routing-agent"


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


class ResponsesSessionManager(BaseSessionManager):
    """Extended session management for Responses API.

    This class extends BaseSessionManager with LangGraph conversation management:
    - Stateful conversation handling
    - Agent routing and specialist agent management
    - Session resumption and metadata persistence
    - Task completion detection and auto-routing

    Used by Responses API for full conversation state management.
    """

    # LangGraph id for the *router*; specialist lock compares proposed handoffs to this value.
    ROUTING_AGENT_NAME = _default_agent_id_resolved()

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
        self._integration_context: dict[str, Any] = {}
        # NormalizedRequest.integration_type for this turn (ticket title merge when PER_TICKET)
        self._integration_type_str: Optional[str] = None
        self._channel_policy: Optional[ChannelBehaviorPolicy] = None

        self._initialize_conversation_state()

    @property
    def effective_router_id(self) -> str:
        if self._channel_policy is not None:
            return effective_router_agent_id(self._channel_policy)
        return self.ROUTING_AGENT_NAME

    def _entry_tier_ids(self) -> frozenset[str]:
        if self._channel_policy is None:
            return frozenset({self.ROUTING_AGENT_NAME})
        return frozenset(
            {
                effective_entry_agent_id(self._channel_policy),
                self.effective_router_id,
            }
        )

    def _allow_auto_return_to_router(self) -> bool:
        if self._channel_policy is None:
            return True
        return self._channel_policy.allow_return_to_router

    def _is_ticket_context_channel(self) -> bool:
        if self._channel_policy is None:
            return False
        return policy_needs_ticket_context(self._channel_policy)

    async def _load_policy_from_request_session(
        self,
        session_id: str,
        inbound_integration_type: Any = None,
    ) -> None:
        row = await self.get_session(session_id)
        if row is None:
            return
        row_type = get_enum_value(row.integration_type)
        if inbound_integration_type is not None:
            inbound = get_enum_value(inbound_integration_type)
            if inbound != row_type:
                logger.warning(
                    "Request integration_type disagrees with session row",
                    session_id=session_id,
                    inbound_integration_type=inbound,
                    row_integration_type=row_type,
                )
        self._integration_type_str = row_type
        pol = policy_from_integration_metadata(
            json_value_as_dict(row.integration_metadata)
        )
        if pol is None:
            raise ChannelBehaviorValidationError(
                f"session {session_id!r} missing "
                f"{CHANNEL_BEHAVIOR_SNAPSHOT_KEY!r} snapshot"
            )
        self._channel_policy = pol

    def _initialize_conversation_state(self) -> None:
        """Initialize conversation state for responses mode."""
        try:
            from .langgraph import ResponsesAgentManager

            self.agent_manager = ResponsesAgentManager()
            assert (
                self.agent_manager is not None
            )  # ResponsesAgentManager() never returns None
            self.agents = list(self.agent_manager.agents_dict.keys())
            logger.info("Loaded agents for responses mode", agents=self.agents)
        except ImportError as e:
            logger.warning(
                "LangGraph components not available",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.agent_manager = None
            self.agents = []
        except Exception as e:
            logger.error(
                "Failed to initialize ResponsesAgentManager",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.agent_manager = None
            self.agents = []

    async def handle_responses_message(
        self,
        text: str,
        request_manager_session_id: Optional[str] = None,
        session_name: Optional[str] = None,
        target_agent_id: Optional[str] = None,
        requires_routing: bool = True,
        integration_context: Optional[dict[str, Any]] = None,
        integration_type: Any = None,
    ) -> str:
        """Handle a message in responses mode with full conversation management."""
        if not self.user_id:
            logger.error("Responses mode not available", user_id=self.user_id)
            return "Error: Responses mode not available"

        if not self.agent_manager:
            logger.error("Agent manager not initialized")
            return "Error: Agent manager not initialized"

        self._integration_context = dict(integration_context or {})
        if integration_type is not None:
            self._integration_type_str = get_enum_value(integration_type)

        # Store the request manager session ID for database updates
        if request_manager_session_id:
            self.request_manager_session_id = request_manager_session_id
            await self._load_policy_from_request_session(
                request_manager_session_id, integration_type
            )
        elif integration_type is not None:
            self._integration_type_str = get_enum_value(integration_type)
            self._channel_policy = resolve_channel_behavior_sync(integration_type)

        if self.request_manager_session_id and self._is_ticket_context_channel():
            await self._persist_ticket_title_merge()

        logger.debug(
            "Handling responses message",
            user_id=self.user_id,
            message_preview=text[:100],
            request_manager_session_id=request_manager_session_id,
            session_name=session_name,
            target_agent_id=target_agent_id,
            requires_routing=requires_routing,
            has_current_session=bool(self.current_session),
            current_agent=self.current_agent_name,
        )

        try:
            # Check if we need to create or resume a session
            if not self.current_session:
                # Try to resume existing session from database
                if request_manager_session_id:
                    logger.debug(
                        "Attempting to resume existing session",
                        request_manager_session_id=request_manager_session_id,
                        user_id=self.user_id,
                    )
                    session_resumed = await self._resume_session_from_database(
                        request_manager_session_id
                    )
                    if session_resumed:
                        logger.info(
                            "Resumed existing session",
                            request_manager_session_id=request_manager_session_id,
                            thread_id=(
                                self.conversation_session.thread_id
                                if self.conversation_session
                                else None
                            ),
                            current_agent=self.current_agent_name,
                        )
                    else:
                        logger.debug(
                            "No existing session found, creating new session",
                            request_manager_session_id=request_manager_session_id,
                            user_id=self.user_id,
                        )

                # If session not resumed, create a new one
                if not self.current_session:
                    logger.debug(
                        "Creating initial session for responses mode",
                        user_id=self.user_id,
                        session_name=session_name,
                        target_agent_id=target_agent_id,
                        requires_routing=requires_routing,
                    )
                    success = await self._create_initial_session(
                        session_name,
                        target_agent_id=target_agent_id,
                        requires_routing=requires_routing,
                    )
                    if not success:
                        logger.error(
                            "Failed to create initial session",
                            user_id=self.user_id,
                            session_name=session_name,
                        )
                        return "Error: Failed to create session"

            # Check if we need to return to routing agent after task completion
            # Check the thread state for the _should_return_to_routing flag
            should_reset = False
            if self.conversation_session:
                try:
                    state = await self.conversation_session.app.aget_state(
                        self.conversation_session.thread_config
                    )
                    # Check for the _should_return_to_routing flag in state
                    if hasattr(state, "values"):
                        should_return = state.values.get(
                            "_should_return_to_routing", False
                        )
                        if should_return:
                            should_reset = True
                            logger.info(
                                "Found _should_return_to_routing flag in state - routing back to routing agent"
                            )
                except Exception as e:
                    logger.debug(
                        "Could not check conversation state",
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            if should_reset:
                if (
                    not self._allow_auto_return_to_router()
                    and self._is_specialist_session()
                ):
                    logger.info(
                        "Ticket-scoped session: ignoring _should_return_to_routing — staying on specialist",
                        user_id=self.user_id,
                        current_agent=self.current_agent_name,
                    )
                else:
                    logger.info(
                        "Specialist task complete, returning to routing agent",
                        user_id=self.user_id,
                        current_agent=self.current_agent_name,
                    )
                    await self._reset_conversation_state()
                    # Recursively call with the actual user message to create new routing session
                    # Return to routing agent - pass None/True to create routing session
                    return await self.handle_responses_message(
                        text,
                        request_manager_session_id,
                        session_name,
                        target_agent_id=None,
                        requires_routing=True,
                        integration_context=self._integration_context,
                        integration_type=self._integration_type_str,
                    )

            # Intercept special commands before passing to conversation
            if text.strip().lower() == "**tokens**":
                logger.debug(
                    "Intercepting **tokens** command",
                    user_id=self.user_id,
                    request_manager_session_id=self.request_manager_session_id,
                )
                return await self._handle_tokens_query()

            # Send message to current session
            logger.debug(
                "Sending message to LangGraph session",
                user_id=self.user_id,
                current_agent=self.current_agent_name,
                thread_id=(
                    self.conversation_session.thread_id
                    if self.conversation_session
                    else None
                ),
            )

            token_context = get_session_token_context(self.request_manager_session_id)
            if self.conversation_session is None:
                logger.error("Conversation session not initialized")
                return "Error: Conversation session not initialized"

            # Raw message input shield: runs before the state machine sees the message
            if self.current_agent_name and self.agent_manager:
                agent = self.agent_manager.get_agent(self.current_agent_name)
                if agent:
                    is_safe, error_message = await agent.check_input_shield(text)
                    if not is_safe:
                        logger.info(
                            "Input blocked by raw message shield",
                            agent_name=self.current_agent_name,
                            user_id=self.user_id,
                        )
                        return (
                            error_message
                            or "I apologize, but I cannot process that request due to safety concerns."
                        )

            state_patch = await self._build_langgraph_state_patch()
            response = await self.conversation_session.send_message(
                text,
                token_context=token_context,
                state_patch=state_patch if state_patch else None,
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

            # Raw response output shield: runs before the response is returned to the user
            if self.current_agent_name and self.agent_manager:
                agent = self.agent_manager.get_agent(self.current_agent_name)
                if agent:
                    is_safe, error_message = await agent.check_output_shield(
                        processed_response
                    )
                    if not is_safe:
                        logger.info(
                            "Output blocked by raw response shield",
                            agent_name=self.current_agent_name,
                            user_id=self.user_id,
                        )
                        return (
                            error_message
                            or "I apologize, but I cannot provide that response due to safety concerns."
                        )

            logger.info(
                "Responses message processed successfully",
                user_id=self.user_id,
                current_agent=self.current_agent_name,
                response_length=len(processed_response),
            )

            return processed_response

        except Exception as e:
            logger.error(
                "Error handling responses message",
                error=str(e),
                error_type=type(e).__name__,
                user_id=self.user_id,
                current_agent=self.current_agent_name,
                message_preview=text[:100],
                exc_info=e,
            )
            return f"Error: {str(e)}"

    async def _create_initial_session(
        self,
        session_name: Optional[str] = None,
        target_agent_id: Optional[str] = None,
        requires_routing: bool = True,
    ) -> bool:
        """Create an initial session for responses mode."""
        try:
            logger.debug(
                "Creating initial session for responses mode",
                user_id=self.user_id,
                session_name=session_name,
                target_agent_id=target_agent_id,
                requires_routing=requires_routing,
            )

            # Get agent: specialist when target_agent_id set and requires_routing=False
            if self.agent_manager is None:
                logger.error(
                    "Agent manager not initialized. Cannot create initial session."
                )
                return False

            use_specialist = target_agent_id is not None and not requires_routing
            default_first = os.getenv("DEFAULT_AGENT_ID", "routing-agent")
            agent_name: str = (
                target_agent_id
                if (use_specialist and target_agent_id)
                else default_first
            )
            if not use_specialist and self.request_manager_session_id:
                db_row = await self.get_session(self.request_manager_session_id)
                if db_row and db_row.current_agent_id:
                    cand = str(db_row.current_agent_id).strip()
                    if cand and self.agent_manager.get_agent(cand):
                        agent_name = cand

            agent = self.agent_manager.get_agent(agent_name)
            if not agent:
                logger.error(
                    "Agent not available",
                    user_id=self.user_id,
                    agent_name=agent_name,
                    available_agents=(
                        list(self.agent_manager.agents_dict.keys())
                        if self.agent_manager
                        else []
                    ),
                )
                return False

            # Debug: Check agent configuration
            lg_config = agent.config.get("lg_state_machine_config")
            logger.info(
                "Agent configuration",
                lg_state_machine_config=lg_config,
                agent_name=agent_name,
            )

            # Generate session name and create session
            session_name = session_name or self._generate_session_name()
            logger.debug(
                "Creating LangGraph session",
                user_id=self.user_id,
                session_name=session_name,
                agent_name=agent_name,
            )

            session = await self._create_session_for_agent(
                agent,
                agent_name,
                session_name=session_name,
            )

            # Debug: Check StateMachine configuration
            logger.info(
                "StateMachine configuration",
                config_path=str(session.config_path),
                initial_state=session.state_machine.config.get("settings", {}).get(
                    "initial_state"
                ),
            )

            # Set up the new session
            self.conversation_session = session
            self.current_agent_name = agent_name
            self.current_session = self._build_session_data(
                agent, agent_name, session, session_name
            )

            logger.debug(
                "Session created successfully",
                user_id=self.user_id,
                session_name=session_name,
                thread_id=session.thread_id,
                current_agent=self.current_agent_name,
            )

            # Update database with current agent
            logger.debug(
                "Updating database session state",
                user_id=self.user_id,
                agent_name=agent_name,
                thread_id=session.thread_id,
            )

            await self._update_database_session_state(
                agent_name,
                session.thread_id,
                self.request_manager_session_id,
            )

            logger.info(
                "Initial session created and database updated",
                user_id=self.user_id,
                session_name=session_name,
                thread_id=session.thread_id,
                current_agent=self.current_agent_name,
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to create new session",
                error=str(e),
                error_type=type(e).__name__,
                user_id=self.user_id,
                session_name=session_name,
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
                    "No existing session found in database",
                    request_manager_session_id=request_manager_session_id,
                    user_id=self.user_id,
                )
                return False

            await self._load_policy_from_request_session(request_manager_session_id)

            # Extract session metadata
            current_agent_id = db_session.current_agent_id
            conversation_thread_id = db_session.conversation_thread_id
            conversation_context = db_session.conversation_context or {}

            if not conversation_thread_id or not current_agent_id:
                logger.debug(
                    "Session found but missing required fields",
                    request_manager_session_id=request_manager_session_id,
                    current_agent_id=current_agent_id,
                    conversation_thread_id=conversation_thread_id,
                )
                return False

            logger.info(
                "Resuming session from database",
                request_manager_session_id=request_manager_session_id,
                current_agent_id=current_agent_id,
                conversation_thread_id=conversation_thread_id,
            )

            # Get the agent
            if self.agent_manager is None:
                logger.error("Agent manager not initialized. Cannot resume session.")
                return False

            agent = self.agent_manager.get_agent(current_agent_id)
            if not agent:
                logger.error(
                    "Agent not found for resumption",
                    agent_id=current_agent_id,
                    available_agents=(
                        list(self.agent_manager.agents_dict.keys())
                        if self.agent_manager
                        else []
                    ),
                )
                return False

            # Create session for agent with existing thread_id
            session_name = conversation_context.get(
                "session_name", f"session-{self.user_id}"
            )
            session = await self._create_session_for_agent(
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

            # Check if the conversation is in a terminal state
            # If it's a specialist agent session that's completed, reset and return to routing
            try:
                state = await session.app.aget_state(session.thread_config)
                if hasattr(state, "values"):
                    current_state = state.values.get("current_state")
                    if (
                        self._is_specialist_session()
                        and session.state_machine.is_terminal_state(current_state)
                    ):
                        if not self._allow_auto_return_to_router():
                            logger.info(
                                "Resumed specialist session is terminal — not resetting to router (channel policy)",
                                request_manager_session_id=request_manager_session_id,
                                current_agent_id=current_agent_id,
                                current_state=current_state,
                            )
                        else:
                            logger.info(
                                "Resumed specialist session is in terminal state - resetting to routing agent",
                                request_manager_session_id=request_manager_session_id,
                                current_agent_id=current_agent_id,
                                current_state=current_state,
                            )
                            # Reset the conversation state
                            await self._reset_conversation_state()
                            # Return False so a new routing session gets created
                            return False
            except Exception as e:
                logger.debug(
                    "Could not check conversation state when resuming session",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Continue with resumption if we can't check the state

            logger.info(
                "Session resumed successfully",
                request_manager_session_id=request_manager_session_id,
                current_agent=self.current_agent_name,
                thread_id=conversation_thread_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to resume session",
                error=str(e),
                error_type=type(e).__name__,
                request_manager_session_id=request_manager_session_id,
                user_id=self.user_id,
                exc_info=e,
            )
            return False

    async def _merge_conversation_context_keys(self, updates: dict[str, Any]) -> None:
        """Merge keys into RequestSession.conversation_context."""
        if not self.request_manager_session_id or not updates:
            return
        try:
            stmt = select(RequestSession).where(
                RequestSession.session_id == self.request_manager_session_id
            )
            result = await self.db_session.execute(stmt)
            row = result.scalar_one_or_none()
            if not row:
                return
            merged: dict[str, Any] = {
                **cast(Dict[str, Any], row.conversation_context or {}),
                **updates,
            }
            await self.db_session.execute(
                update(RequestSession)
                .where(RequestSession.session_id == self.request_manager_session_id)
                .values(
                    conversation_context=merged,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self.db_session.commit()
        except Exception as e:
            logger.warning(
                "Failed to merge conversation_context keys",
                error=str(e),
                user_id=self.user_id,
            )

    async def _persist_ticket_title_merge(self) -> None:
        """Store latest ticket title on the session for prompts and history (PER_TICKET channels)."""
        title = (self._integration_context.get("ticket_title") or "").strip()
        if not title:
            return
        await self._merge_conversation_context_keys({"last_ticket_title": title})

    async def _build_langgraph_state_patch(self) -> dict[str, Any]:
        """Fields merged into LangGraph state for ticket prompts (e.g. ticket title)."""
        if not self._is_ticket_context_channel():
            return {}
        patch: dict[str, Any] = {}
        tt = (self._integration_context.get("ticket_title") or "").strip()
        if not tt and self.request_manager_session_id:
            try:
                stmt = select(RequestSession).where(
                    RequestSession.session_id == self.request_manager_session_id
                )
                result = await self.db_session.execute(stmt)
                row = result.scalar_one_or_none()
                if row:
                    lt = (
                        cast(Dict[str, Any], row.conversation_context or {}).get(
                            "last_ticket_title"
                        )
                        or ""
                    )
                    tt = str(lt).strip()
            except Exception:
                tt = ""
        if tt:
            patch["ticket_title"] = tt
        return patch

    async def _handle_tokens_query(self) -> str:
        """Handle **tokens** command by querying database for session token counts."""
        try:
            if not self.request_manager_session_id:
                return "Token stats not available (no session ID)"

            from shared_models.database import get_db_session
            from shared_models.session_token_service import SessionTokenService

            logger.debug(
                "Querying token counts from database",
                session_id=self.request_manager_session_id,
                user_id=self.user_id,
            )

            async with get_db_session() as db:
                token_counts = await SessionTokenService.get_token_counts(
                    db, self.request_manager_session_id
                )

            if token_counts:
                logger.info(
                    "Token counts retrieved from database",
                    session_id=self.request_manager_session_id,
                    total_tokens=token_counts["total_tokens"],
                    call_count=token_counts["llm_call_count"],
                )
                return f"CURRENT_TOKEN_SUMMARY:INPUT:{token_counts['total_input_tokens']}:OUTPUT:{token_counts['total_output_tokens']}:TOTAL:{token_counts['total_tokens']}:CALLS:{token_counts['llm_call_count']}:MAX_SINGLE_INPUT:{token_counts['max_input_tokens']}:MAX_SINGLE_OUTPUT:{token_counts['max_output_tokens']}:MAX_SINGLE_TOTAL:{token_counts['max_total_tokens']}"
            else:
                logger.debug(
                    "No token counts found for session",
                    session_id=self.request_manager_session_id,
                )
                return "CURRENT_TOKEN_SUMMARY:INPUT:0:OUTPUT:0:TOTAL:0:CALLS:0:MAX_SINGLE_INPUT:0:MAX_SINGLE_OUTPUT:0:MAX_SINGLE_TOTAL:0"

        except Exception as e:
            logger.error(
                "Failed to retrieve token counts",
                error=str(e),
                error_type=type(e).__name__,
                session_id=self.request_manager_session_id,
                exc_info=e,
            )
            return "Token stats not available (error retrieving counts)"

    async def _create_session_for_agent(
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
        # Determine authoritative_user_id for employee lookup (ServiceNow requires email addresses)
        # Priority: 1) explicitly provided, 2) user_email if available, 3) user_id if it's an email (not UUID)
        authoritative_user_id = kwargs.get("authoritative_user_id")
        if authoritative_user_id is None:
            # Always prefer user_email if available (most explicit/authoritative source)
            if self.user_email:
                authoritative_user_id = self.user_email
                logger.debug(
                    "Using user_email as authoritative_user_id",
                    user_email=self.user_email,
                )
            # Fallback to user_id only if it's not a UUID (i.e., it's already an email address)
            elif self.user_id and not is_uuid(self.user_id):
                authoritative_user_id = self.user_id
                logger.debug(
                    "Using user_id as authoritative_user_id (not a UUID)",
                    user_id=self.user_id,
                )
            else:
                # If user_id is a UUID and we have no email, authoritative_user_id will be None
                # This will cause the MCP server to raise an error, which is the correct behavior
                logger.warning(
                    "No email available for authoritative_user_id - user_id is UUID or missing",
                    user_id=self.user_id,
                    user_email=self.user_email,
                    is_uuid=is_uuid(self.user_id) if self.user_id else False,
                )
        else:
            logger.debug(
                "Using provided authoritative_user_id from kwargs",
                authoritative_user_id=authoritative_user_id,
            )

        # Use provided thread_id for resumption or generate a new one
        if resume_thread_id:
            session_thread_id = resume_thread_id
        else:
            session_thread_id = str(uuid.uuid4())

        return await ConversationSession.create(
            agent,
            thread_id=session_thread_id,
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

    def _is_entry_tier_session(self) -> bool:
        """True when the current agent may dispatch to specialists (router or ticket intake)."""
        if not self.current_agent_name:
            return False
        return self.current_agent_name in self._entry_tier_ids()

    def _is_specialist_session(self) -> bool:
        """Check if current session is with a leaf specialist (not entry-tier)."""
        return not self._is_entry_tier_session()

    def _process_agent_response(
        self, response: str, fallback_message: str = "No response received from agent"
    ) -> str:
        """Process and normalize agent response."""
        if response:
            return response.strip()
        return fallback_message

    async def _handle_routing(self, processed_response: str, text: str) -> str:
        """Handle agent routing logic using unified routing detection."""

        logger.debug(
            "Responses API routing check",
            user_id=self.user_id,
            response_preview=processed_response[:100],
            available_agents=self.agents,
            current_agent=self.current_agent_name,
            is_entry_tier_session=self._is_entry_tier_session(),
        )

        if self.conversation_session:
            try:
                current_state = await self.conversation_session.app.aget_state(
                    self.conversation_session.thread_config
                )
                current_values = current_state.values
                current_state_name = current_values.get("current_state", "unknown")
                routing_decision = current_values.get("routing_decision")
                user_intent = current_values.get("user_intent")
                logger.info(
                    "LangGraph state machine state",
                    current_state=current_state_name,
                    routing_decision=routing_decision,
                    user_intent=user_intent,
                    thread_id=self.conversation_session.thread_id,
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
            "Routing analysis",
            full_response=processed_response,
            available_agents=self.agents,
            current_agent=self.current_agent_name,
        )

        # Use StateMachine routing_decision field instead of parsing messages
        routed_agent = None

        # Check conversation state for routing decision from StateMachine
        if self.conversation_session:
            try:
                current_state = await self.conversation_session.app.aget_state(
                    self.conversation_session.thread_config
                )
                current_values = current_state.values
                routing_decision = current_values.get("routing_decision")
                user_intent = current_values.get("user_intent")
                current_state_name = current_values.get("current_state")

                logger.info(
                    "StateMachine state check",
                    current_state=current_state_name,
                    routing_decision=routing_decision,
                    user_intent=user_intent,
                )

                if routing_decision and routing_decision in self.agents:
                    routed_agent = routing_decision
                    logger.info(
                        "Found routing decision from StateMachine", agent=routed_agent
                    )
                else:
                    logger.info(
                        "No valid routing decision in StateMachine state",
                        routing_decision=routing_decision,
                        available_agents=self.agents,
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
                        "Found agent name in response (fallback)",
                        agent=agent_name,
                        signal=signal,
                    )
                    break

        logger.debug("Routing detection result", routed_agent=routed_agent)

        # Specialist lock: on a leaf specialist, ignore routing_decision that would leave the
        # current specialist. PER_TICKET channels with allow_return_to_router=false never
        # auto-return to router (open a new ticket/session to change track).
        if (
            routed_agent
            and self._is_specialist_session()
            and self.current_agent_name
            and routed_agent != self.current_agent_name
        ):
            allow_return_to_router = (
                routed_agent == self.effective_router_id
                and self._allow_auto_return_to_router()
            )
            if not allow_return_to_router:
                logger.info(
                    "Specialist lock: ignoring routing_decision"
                    + (
                        " (channel policy: no auto return-to-router)"
                        if not self._allow_auto_return_to_router()
                        and routed_agent == self.effective_router_id
                        else "; open a new ticket/session to change specialist track"
                    ),
                    user_id=self.user_id,
                    ignored_target=routed_agent,
                    current_agent=self.current_agent_name,
                )
                routed_agent = None

        if routed_agent:
            logger.info(
                "Responses mode routing detected",
                user_id=self.user_id,
                routing_response_preview=processed_response[:100],
                target_agent_name=routed_agent,
                current_agent=self.current_agent_name,
            )

            # Handle task completion - return to router when policy allows
            if (
                routed_agent == self.effective_router_id
                and self._is_specialist_session()
                and self._allow_auto_return_to_router()
            ):
                logger.info(
                    "Specialist task complete, returning to routing agent",
                    user_id=self.user_id,
                    current_agent=self.current_agent_name,
                )
                await self._reset_conversation_state()
                return await self.handle_responses_message(
                    "hi",
                    integration_context=self._integration_context,
                    integration_type=self._integration_type_str,
                )

            # Handle routing to specialist agents
            if (
                routed_agent != self.effective_router_id
                and self._is_entry_tier_session()
            ):
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
                or "task_complete_return_to_router" in response_lower
            ):
                logger.info(
                    "Specialist session termination detected - cleaning response and checking for content",
                    user_id=self.user_id,
                    current_agent=self.current_agent_name,
                )

                # Clean up the response - remove lines with termination markers
                cleaned_response = ""
                if "\n" in processed_response:
                    lines = processed_response.strip().split("\n")
                    clean_lines = [
                        line
                        for line in lines
                        if not any(
                            marker in line.lower()
                            for marker in [
                                "conversation completed",
                                "starting new conversation",
                                "task_complete_return_to_router",
                            ]
                        )
                    ]
                    cleaned_response = "\n".join(clean_lines).strip()
                # For single line with termination marker, treat as no content (cleaned_response = "")

                # If there's actual content after cleaning, return it
                # The _should_return_to_routing flag in LangGraph state will trigger reset on next message
                if cleaned_response:
                    logger.info(
                        "Termination marker found but response has content - returning content, will reset on next message",
                        user_id=self.user_id,
                        cleaned_response_preview=cleaned_response[:100],
                    )
                    return cleaned_response
                else:
                    # Response was only termination markers — reset to router unless policy blocks it.
                    if not self._allow_auto_return_to_router():
                        logger.info(
                            "Channel policy: response was only termination markers — not resetting to router",
                            user_id=self.user_id,
                            current_agent=self.current_agent_name,
                        )
                        return ""
                    logger.info(
                        "Response contains only termination markers - resetting and routing to router",
                        user_id=self.user_id,
                    )
                    await self._reset_conversation_state()

                    # Send placeholder message - ConversationSession will override with routing agent's
                    # configured initial_user_message from YAML (routing.yaml: settings.initial_user_message)
                    return await self.handle_responses_message(
                        "hi",
                        self.request_manager_session_id,
                        None,
                        integration_context=self._integration_context,
                        integration_type=self._integration_type_str,
                    )

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
            session = await self._create_session_for_agent(
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
            state_patch = await self._build_langgraph_state_patch()
            response = await session.send_message(
                text,
                token_context=token_context,
                state_patch=state_patch if state_patch else None,
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

                # Merge conversation_context so ticket metadata persists
                merged_ctx: dict[str, Any] = dict(
                    cast(Dict[str, Any], session.conversation_context or {})
                )
                merged_ctx.update(
                    {
                        "agent_name": agent_name,
                        "session_type": "responses_api",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if self._is_ticket_context_channel():
                    tt_merge = (
                        self._integration_context.get("ticket_title") or ""
                    ).strip()
                    if tt_merge:
                        merged_ctx["last_ticket_title"] = tt_merge

                update_stmt = (
                    update(RequestSession)
                    .where(RequestSession.session_id == session.session_id)
                    .values(
                        current_agent_id=agent_name,
                        conversation_thread_id=thread_id,
                        conversation_context=merged_ctx,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await self.db_session.execute(update_stmt)
                await self.db_session.commit()

                logger.info(
                    "Database session state updated successfully",
                    user_id=self.user_id,
                    session_id=session.session_id,
                    agent_name=agent_name,
                    thread_id=thread_id,
                )
            else:
                logger.warning("No active session found for user", user_id=self.user_id)

        except Exception as e:
            logger.error(
                "Failed to update database session state",
                error=str(e),
                error_type=type(e).__name__,
                user_id=self.user_id,
                agent_name=agent_name,
                thread_id=thread_id,
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
                # Close session (PostgresSaver doesn't need explicit cleanup, but good practice)
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
                request_manager_session_id=self.request_manager_session_id,
            )

            # Use session_id if available to target the specific session
            if self.request_manager_session_id:
                stmt = (
                    update(RequestSession)
                    .where(
                        RequestSession.session_id == self.request_manager_session_id,
                        RequestSession.status == SessionStatus.ACTIVE.value,
                    )
                    .values(
                        current_agent_id=None,
                        conversation_thread_id=None,
                        # Keep status ACTIVE so the session can be resumed/reused
                        # status=SessionStatus.INACTIVE.value,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
            else:
                # Fallback: update all active sessions for user (legacy behavior)
                # This is less precise but needed if session_id is not available
                from shared_models.user_utils import resolve_canonical_user_id

                try:
                    canonical_user_id = await resolve_canonical_user_id(
                        self.user_id,
                        db=self.db_session,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to resolve canonical user_id for session reset",
                        error=str(e),
                        user_id=self.user_id,
                    )
                    return

                stmt = (
                    update(RequestSession)
                    .where(
                        RequestSession.user_id == canonical_user_id,
                        RequestSession.status == SessionStatus.ACTIVE.value,
                    )
                    .values(
                        current_agent_id=None,
                        conversation_thread_id=None,
                        # Keep status ACTIVE so the session can be resumed/reused
                        # status=SessionStatus.INACTIVE.value,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

            # Execute and commit once for both branches
            result = cast(CursorResult[Any], await self.db_session.execute(stmt))
            await self.db_session.commit()

            # Log if no rows were updated
            if result.rowcount == 0:
                logger.warning(
                    "No session updated - session not found, not active, or no active sessions for user",
                    request_manager_session_id=self.request_manager_session_id,
                    user_id=self.user_id,
                )

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
            # Close session (PostgresSaver doesn't need explicit cleanup, but good practice)
            self.conversation_session.close()
        self.current_session = None
        self.current_agent_name = None
        self.conversation_session = None
