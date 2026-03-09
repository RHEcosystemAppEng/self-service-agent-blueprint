"""CloudEvent-driven Agent Service."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from cloudevents.conversion import to_structured
from cloudevents.http import CloudEvent
from fastapi import Depends, FastAPI, HTTPException, Request, status
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from shared_models import (
    BaseSessionManager,
    CloudEventBuilder,
    CloudEventHandler,
    DatabaseUtils,
    EventTypes,
    acquire_agent_session_lock,
    configure_logging,
    create_cloudevent_response,
    create_shared_lifespan,
    generate_fallback_user_id,
    get_database_manager,
    get_db_session_dependency,
    get_db_utc_now,
    get_request_created_at,
    has_earlier_pending_or_processing,
    parse_cloudevent_from_request,
    release_agent_session_lock,
    simple_health_check,
)
from shared_models.models import (
    AgentResponse,
    NormalizedRequest,
    SessionStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession
from tracing_config.auto_tracing import run as auto_tracing_run
from tracing_config.auto_tracing import (
    tracingIsActive,
)

from . import __version__
from .session_manager import ResponsesSessionManager

# Configure structured logging and auto tracing
SERVICE_NAME = "agent-service"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)

# Agent session lock timeout: must be >= AGENT_TIMEOUT so queued requests can wait
_AGENT_LOCK_TIMEOUT = int(os.getenv("SESSION_LOCK_WAIT_TIMEOUT", "180"))


async def _handle_event_with_try_claim(
    db: AsyncSession,
    event_id: Optional[str],
    event_type: str,
    event_source: str,
    event_data: Dict[str, Any],
    handler: Callable[[], Awaitable[Dict[str, Any]]],
    extract_ids: Callable[
        [Dict[str, Any], Dict[str, Any]], tuple[Optional[str], Optional[str]]
    ],
) -> Dict[str, Any]:
    """Try-claim event; run handler; update processed status. Skips if already claimed."""
    if event_id:
        claimed = await DatabaseUtils.try_claim_event_for_processing(
            db,
            event_id,
            event_type,
            event_source,
            "agent-service",
        )
        if not claimed:
            logger.info(
                "Event already claimed - skipping duplicate",
                event_id=event_id,
                event_type=event_type,
            )
            return {
                "status": "skipped",
                "reason": "duplicate event (already claimed)",
                "event_id": event_id,
            }

    try:
        result = await handler()
        if event_id:
            request_id, session_id = extract_ids(result, event_data)
            await DatabaseUtils.update_processed_event(
                db,
                event_id,
                "agent-service",
                request_id=request_id,
                session_id=session_id,
                processing_result="success",
            )
        return result
    except Exception as e:
        if event_id:
            # For retriable errors (503, 502, 504), release the claim so broker retry
            # can re-claim and process. Marking as "error" would cause try_claim to
            # skip forever—requests would never complete.
            is_retriable = False
            if isinstance(e, HTTPException):
                is_retriable = e.status_code in (502, 503, 504)
            if is_retriable:
                await DatabaseUtils.release_event_claim(db, event_id, "agent-service")
            else:
                await DatabaseUtils.update_processed_event(
                    db,
                    event_id,
                    "agent-service",
                    processing_result="error",
                    error_message="Processing failed",
                )
        raise


class AgentConfig:
    """Configuration for agent service."""

    def __init__(self) -> None:
        self.broker_url = os.getenv("BROKER_URL")

        # BROKER_URL is required for eventing-based communication
        if not self.broker_url:
            raise ValueError(
                "BROKER_URL environment variable is required. "
                "Configure BROKER_URL to point to your Knative broker or mock eventing service."
            )


class AgentService:
    """Service for handling agent interactions."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _is_reset_command(self, content: str) -> bool:
        """Check if the content is a reset command."""
        if not content:
            return False

        content_lower = content.strip().lower()
        reset_commands = ["reset", "clear", "restart", "new session"]
        return content_lower in reset_commands

    def _is_tokens_command(self, content: str) -> bool:
        """Check if the content is a tokens command."""
        if not content:
            return False

        content_lower = content.strip().lower()
        tokens_commands = ["**tokens**", "tokens", "token stats", "usage stats"]
        return content_lower in tokens_commands

    async def _handle_reset_command(self, request: NormalizedRequest) -> AgentResponse:
        """Handle reset command by clearing the session."""
        try:
            # Get database session for session management
            from shared_models import get_database_manager

            db_manager = get_database_manager()

            async with db_manager.get_session() as db:
                session_manager = BaseSessionManager(db)

                # Clear the session by setting it to INACTIVE
                await session_manager.update_session(
                    request.session_id,
                    status=SessionStatus.INACTIVE,
                    agent_id=None,
                    conversation_thread_id=None,
                )

                logger.info(
                    "Session reset completed",
                    session_id=request.session_id,
                    user_id=request.user_id,
                    integration_type=request.integration_type,
                )

                # Return a simple reset confirmation
                return self._create_system_response(
                    request=request,
                    content="Session cleared. Starting fresh!",
                )

        except Exception as e:
            logger.error(
                "Failed to reset session", error=str(e), session_id=request.session_id
            )
            return self._create_error_response(
                request=request,
                content="Failed to reset session. Please try again.",
            )

    async def _handle_tokens_command(self, request: NormalizedRequest) -> AgentResponse:
        """Handle tokens command by fetching token statistics from database."""
        try:
            from shared_models.database import get_db_session
            from shared_models.session_token_service import SessionTokenService

            # Debug logging
            logger.debug(
                "Retrieving token stats from database",
                session_id=request.session_id,
            )

            # Query database for token counts
            async with get_db_session() as db:
                token_counts = await SessionTokenService.get_token_counts(
                    db, request.session_id
                )

            if token_counts:
                # Format the response with all token metrics including max values
                token_summary = f"TOKEN_SUMMARY:INPUT:{token_counts['total_input_tokens']}:OUTPUT:{token_counts['total_output_tokens']}:TOTAL:{token_counts['total_tokens']}:CALLS:{token_counts['llm_call_count']}:MAX_SINGLE_INPUT:{token_counts['max_input_tokens']}:MAX_SINGLE_OUTPUT:{token_counts['max_output_tokens']}:MAX_SINGLE_TOTAL:{token_counts['max_total_tokens']}"

                logger.info(
                    "Token statistics retrieved from database",
                    request_id=request.request_id,
                    session_id=request.session_id,
                    total_tokens=token_counts["total_tokens"],
                    call_count=token_counts["llm_call_count"],
                )

                return self._create_agent_response(
                    request=request,
                    content=token_summary,
                    agent_id="system",
                    response_type="tokens",
                    metadata={
                        "total_input_tokens": token_counts["total_input_tokens"],
                        "total_output_tokens": token_counts["total_output_tokens"],
                        "total_tokens": token_counts["total_tokens"],
                        "call_count": token_counts["llm_call_count"],
                        "max_input_tokens": token_counts["max_input_tokens"],
                        "max_output_tokens": token_counts["max_output_tokens"],
                        "max_total_tokens": token_counts["max_total_tokens"],
                    },
                    processing_time_ms=0,
                )
            else:
                # Session not found or no token counts yet
                return self._create_agent_response(
                    request=request,
                    content="TOKEN_SUMMARY:INPUT:0:OUTPUT:0:TOTAL:0:CALLS:0:MAX_SINGLE_INPUT:0:MAX_SINGLE_OUTPUT:0:MAX_SINGLE_TOTAL:0",
                    agent_id="system",
                    response_type="tokens",
                    metadata={
                        "total_input_tokens": 0,
                        "total_output_tokens": 0,
                        "total_tokens": 0,
                        "call_count": 0,
                        "max_input_tokens": 0,
                        "max_output_tokens": 0,
                        "max_total_tokens": 0,
                    },
                    processing_time_ms=0,
                )

        except Exception as e:
            logger.error(
                "Failed to get token statistics",
                error=str(e),
                request_id=request.request_id,
            )
            return self._create_error_response(
                request=request,
                content="Failed to retrieve token statistics. Please try again.",
            )

    async def process_request(self, request: NormalizedRequest) -> AgentResponse:
        """Process a normalized request and return agent response."""
        return await self._process_request_core(request)

    async def _process_request_core(self, request: NormalizedRequest) -> AgentResponse:
        """Core request processing logic."""
        # Use DB time for agent_received_at (avoids pod clock skew across replicas)
        start_time = await get_db_utc_now()

        try:
            # Check for reset command first
            if self._is_reset_command(request.content):
                return await self._handle_reset_command(request)

            # Check for tokens command
            if self._is_tokens_command(request.content):
                return await self._handle_tokens_command(request)

            # Publish processing started event for user notification
            await self._publish_processing_event(request)

            return await self._handle_responses_mode_request(request, start_time)

        except Exception as e:
            logger.error(
                "Failed to process request", error=str(e), request_id=request.request_id
            )

            # Return error response
            return self._create_error_response(
                request=request,
                content=f"I apologize, but I encountered an error processing your request: {str(e)}",
                agent_id="unknown",
                start_time=start_time,
            )

    async def publish_response(self, response: AgentResponse) -> bool:
        """Publish agent response as CloudEvent and update database."""
        try:
            # Debug log the response object to see what values it has
            logger.debug(
                "AgentResponse object details",
                request_id=response.request_id,
                session_id=response.session_id,
                user_id=response.user_id,
                agent_id=response.agent_id,
                content_preview=response.content[:100] if response.content else "None",
                response_type=response.response_type,
                processing_time_ms=response.processing_time_ms,
            )

            # Update RequestLog in database first (for CLI sync requests)
            logger.info(
                "Updating RequestLog in database", request_id=response.request_id
            )
            await self._update_request_log(response)
            logger.info(
                "RequestLog updated successfully", request_id=response.request_id
            )

            event_data = {
                "request_id": response.request_id,
                "session_id": response.session_id,
                "user_id": response.user_id,  # Include user_id for Integration Dispatcher
                "agent_id": response.agent_id,
                "content": response.content,
                "response_type": response.response_type,
                "metadata": response.metadata,
                "processing_time_ms": response.processing_time_ms,
                "requires_followup": response.requires_followup,
                "followup_actions": response.followup_actions,
                "created_at": response.created_at.isoformat(),
                "agent_received_at": (
                    response.agent_received_at.isoformat()
                    if response.agent_received_at
                    else None
                ),
            }

            # Debug log the event_data to see what values are being sent
            logger.debug(
                "Event data being published",
                event_data_keys=list(event_data.keys()),
                event_data_values={
                    key: value
                    for key, value in event_data.items()
                    if key
                    in ["request_id", "session_id", "user_id", "agent_id", "content"]
                },
                response_id=response.request_id,
            )

            logger.debug(
                "Publishing agent response event",
                event_data=event_data,
                response_id=response.request_id,
            )

            # Use shared CloudEvent builder with correct event type
            builder = CloudEventBuilder("agent-service")
            event = builder.create_response_event(
                event_data,
                response.request_id,
                response.agent_id,
                response.session_id,
            )

            headers, body = to_structured(event)
            headers = dict(headers)
            # Ce-partitionkey header for Knative Kafka broker
            partition_key = event.get("partitionkey") or event.get("partitionKey")
            if partition_key:
                headers["ce-partitionkey"] = str(partition_key)

            if self.config.broker_url is None:
                logger.error("Broker URL not configured")
                return False

            response_http = await self.http_client.post(
                self.config.broker_url,
                headers=headers,
                content=body,
            )

            response_http.raise_for_status()
            return True

        except Exception as e:
            logger.error("Failed to publish response event", exc_info=e)
            return False

    def _create_agent_response(
        self,
        request: NormalizedRequest,
        content: str,
        agent_id: str,
        response_type: str = "message",
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
        start_time: Optional[datetime] = None,
        requires_followup: bool = False,
        followup_actions: Optional[List[str]] = None,
    ) -> AgentResponse:
        """Create an AgentResponse with consistent defaults.

        Args:
            request: The normalized request
            content: Response content
            agent_id: Agent identifier (required)
            response_type: Type of response (default: "message")
            metadata: Optional metadata dictionary
            processing_time_ms: Processing time in milliseconds (if None and start_time provided, will calculate)
            start_time: Start time for processing (used to calculate processing_time_ms if not provided)
            requires_followup: Whether response requires followup
            followup_actions: List of followup actions
        """
        # Calculate processing time if start_time provided and processing_time_ms not specified
        if processing_time_ms is None and start_time is not None:
            processing_time_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        # Use provided metadata or empty dict
        response_metadata = dict(metadata) if metadata else {}

        response = AgentResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            agent_id=agent_id,
            content=content,
            response_type=response_type,
            metadata=response_metadata,
            processing_time_ms=processing_time_ms,
            requires_followup=requires_followup,
            followup_actions=followup_actions or [],
            created_at=datetime.now(timezone.utc),
            agent_received_at=start_time,
        )
        return response

    def _create_error_response(
        self,
        request: NormalizedRequest,
        content: str,
        agent_id: str = "system",
        start_time: Optional[datetime] = None,
    ) -> AgentResponse:
        """Create an error response with common defaults."""
        return self._create_agent_response(
            request=request,
            content=content,
            agent_id=agent_id,
            response_type="error",
            processing_time_ms=0,
            start_time=start_time,
        )

    def _create_system_response(
        self,
        request: NormalizedRequest,
        content: str,
        start_time: Optional[datetime] = None,
    ) -> AgentResponse:
        """Create a system response with common defaults."""
        return self._create_agent_response(
            request=request,
            content=content,
            agent_id="system",
            processing_time_ms=0,
            start_time=start_time,
        )

    async def _update_request_log(self, response: AgentResponse) -> None:
        """Update RequestLog in database with response content."""
        if response.agent_id is None:
            logger.error(
                "Cannot update request log - response missing agent_id",
                request_id=response.request_id,
                session_id=response.session_id,
            )
            return

        # status = completed for message/tokens, failed for error
        status = "completed" if response.response_type != "error" else "failed"

        response_metadata = dict(response.metadata) if response.metadata else {}
        if response.agent_received_at:
            response_metadata["agent_received_at"] = (
                response.agent_received_at.isoformat()
            )
        await _update_request_log_unified(
            request_id=response.request_id,
            response_content=response.content,
            agent_id=response.agent_id,
            response_metadata=response_metadata,
            processing_time_ms=response.processing_time_ms,
            status=status,
            db=None,  # Will create its own database session
        )

    async def _handle_responses_mode_request(
        self, request: NormalizedRequest, start_time: datetime
    ) -> AgentResponse:
        """Handle responses mode requests using LangGraph session manager."""
        try:
            from shared_models import get_database_manager

            # Handle session management (increment request count) for responses mode
            await self._handle_session_management(
                request.session_id, request.request_id
            )

            # Get database session for responses session manager
            db_manager = get_database_manager()

            async with db_manager.get_session() as db:
                # Create responses session manager
                session_manager = ResponsesSessionManager(
                    db_session=db,
                    user_id=request.user_id,
                )

                # Process the message using responses mode with session-specific context
                response_content = await session_manager.handle_responses_message(
                    text=request.content,
                    request_manager_session_id=request.session_id,
                    target_agent_id=request.target_agent_id,
                    requires_routing=request.requires_routing,
                )

                # Create response with automatic timing calculation
                if session_manager.current_agent_name is None:
                    logger.warning(
                        "No agent assigned after processing message - retrying with routing session",
                        request_id=request.request_id,
                        session_id=request.session_id,
                    )
                    # Retry processing the message - this should create a routing session
                    # if one doesn't exist (handle_responses_message handles session creation)
                    try:
                        response_content = (
                            await session_manager.handle_responses_message(
                                text=request.content,
                                request_manager_session_id=request.session_id,
                                target_agent_id=request.target_agent_id,
                                requires_routing=request.requires_routing,
                            )
                        )
                        # Check again after retry
                        if session_manager.current_agent_name is None:
                            logger.error(
                                "No agent assigned after retry - cannot process request",
                                request_id=request.request_id,
                                session_id=request.session_id,
                            )
                            return self._create_error_response(
                                request=request,
                                content="Error: No agent assigned to handle this request",
                            )
                    except Exception as e:
                        logger.error(
                            "Exception while retrying message processing",
                            request_id=request.request_id,
                            session_id=request.session_id,
                            error=str(e),
                        )
                        return self._create_error_response(
                            request=request,
                            content="Error: No agent assigned to handle this request",
                        )

                return self._create_agent_response(
                    request=request,
                    content=response_content,
                    agent_id=session_manager.current_agent_name,
                    start_time=start_time,
                )

        except Exception as e:
            logger.error(
                "Failed to handle responses mode request",
                error=str(e),
                request_id=request.request_id,
                session_id=request.session_id,
            )
            return self._create_error_response(
                request=request,
                content=f"Failed to process responses mode request: {str(e)}",
            )

    async def _publish_processing_event(self, request: NormalizedRequest) -> bool:
        """Publish processing started event for user notification."""
        try:
            event_data = {
                "request_id": request.request_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "integration_type": request.integration_type,
                "request_type": request.request_type,
                "content_preview": (
                    request.content[:100] + "..."
                    if len(request.content) > 100
                    else request.content
                ),
                "target_agent_id": request.target_agent_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            event = CloudEvent(
                {
                    "specversion": "1.0",
                    "type": EventTypes.REQUEST_PROCESSING,
                    "source": "agent-service",
                    "id": str(uuid.uuid4()),
                    "time": datetime.now(timezone.utc).isoformat(),
                    "subject": f"session/{request.session_id}",
                    "datacontenttype": "application/json",
                },
                event_data,
            )

            headers, body = to_structured(event)

            if self.config.broker_url is None:
                logger.error("Broker URL not configured")
                return False

            response = await self.http_client.post(
                self.config.broker_url,
                headers=headers,
                content=body,
            )

            response.raise_for_status()

            logger.info(
                "Processing event published",
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=request.user_id,
            )

            return True

        except Exception as e:
            logger.error("Failed to publish processing event", exc_info=e)
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()

    async def _handle_session_management(
        self, session_id: str, request_id: str
    ) -> None:
        """Handle session management including request count increment.

        This method ensures consistent session management across all requests.
        """
        try:
            # Get database session for session management
            db_manager = get_database_manager()
            async with db_manager.get_session() as db:
                session_manager = BaseSessionManager(db)
                await session_manager.increment_request_count(session_id, request_id)

                logger.debug(
                    "Session management completed",
                    session_id=session_id,
                    request_id=request_id,
                )
        except Exception as e:
            logger.warning(
                "Failed to handle session management",
                session_id=session_id,
                request_id=request_id,
                error=str(e),
            )
            # Don't raise exception - session management failure shouldn't stop request processing


# Global agent service instance
_agent_service: Optional[AgentService] = None


async def _agent_service_startup() -> None:
    """Custom startup logic for Agent Service."""
    global _agent_service

    config = AgentConfig()
    _agent_service = AgentService(config)
    logger.info("Agent Service initialized")


async def _agent_service_shutdown() -> None:
    """Custom shutdown logic for Agent Service."""
    global _agent_service

    if _agent_service:
        await _agent_service.close()
        _agent_service = None


# Create lifespan using shared utility with custom startup/shutdown
def lifespan(app: FastAPI) -> Any:
    return create_shared_lifespan(
        service_name="agent-service",
        version=__version__,
        custom_startup=_agent_service_startup,
        custom_shutdown=_agent_service_shutdown,
    )


# Create FastAPI application
app = FastAPI(
    title="Self-Service Agent Service",
    description="CloudEvent-driven Agent Service",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint - lightweight without database dependency."""
    return {
        "status": "healthy",
        "service": "agent-service",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Detailed health check with database dependency for monitoring."""
    return dict(
        await simple_health_check(
            service_name="agent-service",
            version=__version__,
            db=db,
        )
    )


@app.post("/api/v1/events/cloudevents")
async def handle_cloudevent(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Handle incoming CloudEvents."""
    if not _agent_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service not initialized",
        )

    try:
        # Parse CloudEvent from request using shared utility
        event_data = await parse_cloudevent_from_request(request)

        event_type = event_data.get("type")
        event_id = event_data.get("id")
        event_source = event_data.get("source", "unknown")

        # Handle request events
        if event_type == EventTypes.REQUEST_CREATED:
            return await _handle_event_with_try_claim(
                db,
                event_id,
                event_type,
                event_source,
                event_data,
                lambda: _handle_request_event_from_data(event_data, _agent_service),
                lambda result, _: (result.get("request_id"), result.get("session_id")),
            )

        # Handle database update events
        if event_type == EventTypes.DATABASE_UPDATE_REQUESTED:
            return await _handle_event_with_try_claim(
                db,
                event_id,
                event_type,
                event_source,
                event_data,
                lambda: _handle_database_update_event_from_data(
                    event_data, _agent_service
                ),
                lambda _, ev: (
                    ev.get("data", {}).get("request_id"),
                    ev.get("data", {}).get("session_id"),
                ),
            )

        logger.warning("Unhandled CloudEvent type", event_type=event_type)
        return dict(
            await create_cloudevent_response(
                status="ignored",
                message="Unhandled event type",
                details={"event_type": event_type},
            )
        )

    except HTTPException:
        # Re-raise so 503 (ordering check, lock timeout) propagates for broker retry
        raise
    except Exception as e:
        logger.error("Failed to handle CloudEvent", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


def _create_normalized_request_from_data(
    request_data: Dict[str, Any],
) -> NormalizedRequest:
    """Create a NormalizedRequest from request data with proper validation."""
    # Validate required fields
    required_fields = [
        "request_id",
        "session_id",
        "user_id",
        "integration_type",
        "request_type",
        "content",
    ]
    missing_fields = [field for field in required_fields if not request_data.get(field)]

    if missing_fields:
        raise ValueError(f"Missing required fields in request data: {missing_fields}")

    return NormalizedRequest(
        request_id=request_data["request_id"],
        session_id=request_data["session_id"],
        user_id=request_data["user_id"],
        integration_type=request_data["integration_type"],
        request_type=request_data["request_type"],
        content=request_data["content"],
        integration_context=request_data.get("integration_context", {}),
        user_context=request_data.get("user_context", {}),
        target_agent_id=request_data.get("target_agent_id"),
        requires_routing=request_data.get("requires_routing", True),
        created_at=datetime.fromisoformat(
            request_data.get("created_at", datetime.now().isoformat())
        ),
    )


async def _handle_request_event_from_data(
    event_data: Dict[str, Any], agent_service: AgentService
) -> Dict[str, Any]:
    """Handle request CloudEvent using pre-parsed event data."""
    try:
        # Extract event data using common utility
        request_data = CloudEventHandler.extract_event_data(event_data)

        # Parse normalized request with proper error handling
        try:
            request = _create_normalized_request_from_data(request_data)

            logger.debug(
                "Created NormalizedRequest",
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=request.user_id,
                content_preview=request.content[:100] if request.content else "empty",
            )
        except Exception as e:
            logger.error(
                "Failed to parse normalized request",
                error=str(e),
                event_data=event_data,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request data: {str(e)}",
            )

        # Resolve created_at: use event payload if present, else fetch from RequestLog
        # (request-manager inserts before sending; DB time is source of truth for ordering)
        created_at = request.created_at
        if "created_at" not in request_data:
            db_manager = get_database_manager()
            async with db_manager.get_session() as resolve_db:
                db_created = await get_request_created_at(
                    request.request_id, resolve_db
                )
                if db_created is not None:
                    created_at = db_created
                    request = request.model_copy(update={"created_at": created_at})

        # Ordering check: yield (503) if earlier request still pending/processing
        # Defense in depth alongside partition key; broker retries later
        db_manager = get_database_manager()
        async with db_manager.get_session() as lock_db:
            if await has_earlier_pending_or_processing(
                request.session_id, created_at, lock_db
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Earlier request still processing - retry later",
                )

            acquired = await acquire_agent_session_lock(
                request.session_id, lock_db, timeout_seconds=_AGENT_LOCK_TIMEOUT
            )
            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Session lock timeout - another request for this session is processing",
                )
            try:
                logger.debug("Calling agent_service.process_request")
                response = await agent_service.process_request(request)
            finally:
                await release_agent_session_lock(request.session_id, lock_db)

        logger.debug(
            "Agent response created",
            response_id=response.request_id if response else "None",
            response_type=type(response).__name__ if response else "None",
        )

        # Publish response event
        logger.debug("Publishing response event")
        success = await agent_service.publish_response(response)

        logger.info(
            "Request processed",
            request_id=request.request_id,
            session_id=request.session_id,
            agent_id=response.agent_id,
            response_published=success,
        )

        return {
            "request_id": response.request_id,
            "session_id": response.session_id,
            "user_id": response.user_id,
            "agent_id": response.agent_id,
            "content": response.content,
            "response_type": response.response_type,
            "metadata": response.metadata,
            "processing_time_ms": response.processing_time_ms,
            "requires_followup": response.requires_followup,
            "followup_actions": response.followup_actions,
            "created_at": response.created_at.isoformat(),
        }

    except Exception as e:
        logger.error("Failed to handle request event", exc_info=e)
        raise


async def _handle_database_update_event_from_data(
    event_data: Dict[str, Any], agent_service: AgentService
) -> Dict[str, Any]:
    """Handle database update event from Request Manager using pre-parsed event data."""
    try:
        # Extract the actual update data from the CloudEvent data field
        update_data = event_data.get("data", {})

        request_id = update_data.get("request_id")
        session_id = update_data.get("session_id")
        agent_id = update_data.get("agent_id")
        content = update_data.get("content")
        user_id = update_data.get("user_id")

        if not all([request_id, session_id, agent_id, content]):
            raise ValueError("Missing required fields in database update event")

        if not user_id:
            logger.warning(
                "Missing user_id in database update event, using fallback",
                request_id=request_id,
                session_id=session_id,
            )
            user_id = generate_fallback_user_id(request_id)

        logger.info(
            "Database update event received from Request Manager",
            request_id=request_id,
            session_id=session_id,
            agent_id=agent_id,
        )

        return {
            "status": "updated",
            "request_id": request_id,
            "session_id": session_id,
            "agent_id": agent_id,
        }

    except Exception as e:
        logger.error("Failed to handle database update event", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process database update event",
        )


async def _update_request_log_unified(
    request_id: str,
    response_content: str,
    agent_id: str,
    response_metadata: dict[str, Any] | None = None,
    processing_time_ms: int | None = None,
    status: str = "completed",
    db: AsyncSession | None = None,
) -> None:
    """Update RequestLog for any API type. Sets status (completed/failed) per response_type."""
    try:
        from shared_models.models import RequestLog
        from sqlalchemy import update

        # Update the RequestLog with response content and status
        stmt = (
            update(RequestLog)
            .where(RequestLog.request_id == request_id)
            .values(
                response_content=response_content,
                response_metadata=response_metadata or {},
                agent_id=agent_id,
                processing_time_ms=processing_time_ms,
                completed_at=datetime.now(timezone.utc),
                status=status,
            )
        )

        if db:
            await db.execute(stmt)
            await db.commit()
        else:
            # For backward compatibility with existing code that doesn't pass db
            from shared_models import get_database_manager

            db_manager = get_database_manager()
            async with db_manager.get_session() as session:
                await session.execute(stmt)
                await session.commit()

        logger.info(
            "RequestLog updated",
            request_id=request_id,
            agent_id=agent_id,
            content_length=len(response_content),
        )

    except Exception as e:
        logger.error(
            "Failed to update RequestLog",
            request_id=request_id,
            error=str(e),
        )
        # Don't raise exception - RequestLog update failure shouldn't stop response


if tracingIsActive():
    FastAPIInstrumentor.instrument_app(app)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "agent_service.main:app",
        host=host,
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info",
    )
