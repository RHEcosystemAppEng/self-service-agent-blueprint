"""CloudEvent-driven Agent Service."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from cloudevents.http import CloudEvent, to_structured
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from shared_clients.stream_processor import LlamaStackStreamProcessor
from shared_models import (
    CloudEventBuilder,
    CloudEventHandler,
    EventTypes,
    configure_logging,
    create_cloudevent_response,
    create_shared_lifespan,
    generate_fallback_user_id,
    get_database_manager,
    get_db_session_dependency,
    parse_cloudevent_from_request,
    simple_health_check,
)
from shared_models.models import AgentResponse, NormalizedRequest, SessionStatus
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .schemas import SessionCreate, SessionResponse, SessionUpdate
from .session_manager import BaseSessionManager, ResponsesSessionManager

# Configure structured logging
logger = configure_logging("agent-service")


class AgentConfig:
    """Configuration for agent service."""

    def __init__(self) -> None:
        self.llama_stack_url = os.getenv("LLAMA_STACK_URL", "http://llamastack:8321")
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
        """Handle tokens command by fetching token statistics from asset_manager."""
        try:
            from asset_manager.token_counter import get_token_stats

            # Use session-specific token stats, with fallback to global stats
            # The get_stats method now falls back to global stats when context doesn't exist
            from .session_manager import get_session_token_context

            token_context = get_session_token_context(request.session_id)

            # Debug logging to see what context is being used
            logger.debug(
                "Retrieving token stats",
                session_id=request.session_id,
                token_context=token_context,
            )

            context_stats = get_token_stats(context=token_context)

            # Format the response similar to the original chat.py
            token_summary = f"TOKEN_SUMMARY:INPUT:{context_stats.total_input_tokens}:OUTPUT:{context_stats.total_output_tokens}:TOTAL:{context_stats.total_tokens}:CALLS:{context_stats.call_count}:MAX_SINGLE_INPUT:{context_stats.max_input_tokens}:MAX_SINGLE_OUTPUT:{context_stats.max_output_tokens}:MAX_SINGLE_TOTAL:{context_stats.max_total_tokens}"

            logger.info(
                "Token statistics retrieved with fallback",
                request_id=request.request_id,
                session_id=request.session_id,
                token_context=token_context,
                total_tokens=context_stats.total_tokens,
                call_count=context_stats.call_count,
            )

            return self._create_agent_response(
                request=request,
                content=token_summary,
                agent_id="system",
                response_type="tokens",
                metadata={
                    "total_input_tokens": context_stats.total_input_tokens,
                    "total_output_tokens": context_stats.total_output_tokens,
                    "total_tokens": context_stats.total_tokens,
                    "call_count": context_stats.call_count,
                    "max_input_tokens": context_stats.max_input_tokens,
                    "max_output_tokens": context_stats.max_output_tokens,
                    "max_total_tokens": context_stats.max_total_tokens,
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
        start_time = datetime.now(timezone.utc)

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

        response = AgentResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            agent_id=agent_id,
            content=content,
            response_type=response_type,
            metadata=metadata or {},
            processing_time_ms=processing_time_ms,
            requires_followup=requires_followup,
            followup_actions=followup_actions or [],
            created_at=datetime.now(timezone.utc),
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

        await _update_request_log_unified(
            request_id=response.request_id,
            response_content=response.content,
            agent_id=response.agent_id,
            response_metadata=response.metadata,
            processing_time_ms=response.processing_time_ms,
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
                )

                # Create response with automatic timing calculation
                if session_manager.current_agent_name is None:
                    logger.error(
                        "Cannot create agent response - no agent assigned",
                        request_id=request.request_id,
                        session_id=request.session_id,
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


@app.post("/process", response_model=None)
async def handle_direct_request(
    request: Request, stream: bool = False
) -> StreamingResponse | Dict[str, Any]:
    """Handle direct HTTP requests with optional streaming support."""
    if not _agent_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service not initialized",
        )

    try:
        body = await request.body()
        request_data = json.loads(body)

        logger.info(
            "Direct request received",
            request_id=request_data.get("request_id"),
            session_id=request_data.get("session_id"),
            user_id=request_data.get("user_id"),
            stream=stream,
        )

        # Create a normalized request for processing
        normalized_request = _create_normalized_request_from_data(request_data)

        if stream:
            # Return streaming response
            async def generate_stream() -> Any:
                try:
                    # Process the request using the agent service
                    agent_response = await _agent_service.process_request(
                        normalized_request
                    )

                    # Stream the response as Server-Sent Events using shared utilities
                    yield LlamaStackStreamProcessor.create_sse_start_event(
                        agent_response.request_id
                    )

                    # Stream the content using optimized streaming
                    async for (
                        chunk_data
                    ) in LlamaStackStreamProcessor.stream_content_optimized(
                        agent_response.content,
                        content_type="content",
                    ):
                        yield chunk_data

                    # Send completion event
                    if (
                        agent_response.agent_id is None
                        or agent_response.processing_time_ms is None
                    ):
                        logger.error(
                            "Cannot send completion event - missing agent_id or processing_time_ms",
                            request_id=agent_response.request_id,
                            session_id=agent_response.session_id,
                            agent_id=agent_response.agent_id,
                            processing_time_ms=agent_response.processing_time_ms,
                        )
                        yield LlamaStackStreamProcessor.create_sse_error_event(
                            "Missing required response data"
                        )
                    else:
                        yield LlamaStackStreamProcessor.create_sse_complete_event(
                            agent_response.agent_id,
                            agent_response.processing_time_ms,
                        )

                except Exception as e:
                    logger.error("Error in streaming response", exc_info=e)
                    yield LlamaStackStreamProcessor.create_sse_error_event(str(e))

            return LlamaStackStreamProcessor.create_sse_response(generate_stream())
        else:
            # Return JSON response using existing CloudEvent handler
            result = await _handle_request_event_from_data(
                {"data": request_data}, _agent_service
            )
            return result

    except json.JSONDecodeError:
        logger.error("Invalid JSON in direct request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error("Error handling direct request", exc_info=e)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/process/stream")
async def handle_direct_request_stream(
    request: Request,
) -> StreamingResponse:
    """Handle direct HTTP requests with streaming responses (legacy endpoint)."""
    # Redirect to unified endpoint with streaming enabled
    return await handle_direct_request(request, stream=True)  # type: ignore[return-value]


@app.post("/api/v1/events/cloudevents")
async def handle_cloudevent(request: Request) -> Dict[str, Any]:
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

        # Handle request events
        if event_type == EventTypes.REQUEST_CREATED:
            return await _handle_request_event_from_data(event_data, _agent_service)

        # Handle database update events
        if event_type == EventTypes.DATABASE_UPDATE_REQUESTED:
            return await _handle_database_update_event_from_data(
                event_data, _agent_service
            )

        logger.warning("Unhandled CloudEvent type", event_type=event_type)
        return dict(
            await create_cloudevent_response(
                status="ignored",
                message="Unhandled event type",
                details={"event_type": event_type},
            )
        )

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

        # Process the request
        logger.debug("Calling agent_service.process_request")
        response = await agent_service.process_request(request)

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


# Session Management Endpoints


@app.post("/api/v1/sessions", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> SessionResponse:
    """Create a new session."""
    session_manager = BaseSessionManager(db)

    try:
        session = await session_manager.create_session(session_data)
        return session
    except Exception as e:
        logger.error("Failed to create session", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


@app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> SessionResponse:
    """Get session information."""
    session_manager = BaseSessionManager(db)

    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return session


@app.put("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_update: SessionUpdate,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> SessionResponse:
    """Update session information."""
    session_manager = BaseSessionManager(db)

    # Check if session exists
    existing_session = await session_manager.get_session(session_id)
    if not existing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Update session with provided fields
    updated_session = await session_manager.update_session(
        session_id=session_id,
        agent_id=session_update.current_agent_id,
        conversation_thread_id=session_update.conversation_thread_id,
        status=session_update.status,
        conversation_context=session_update.conversation_context,
        user_context=session_update.user_context,
    )

    if not updated_session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session",
        )

    return updated_session


@app.post("/api/v1/sessions/{session_id}/increment")
async def increment_request_count(
    session_id: str,
    request_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, str]:
    """Increment the request count for a session."""
    session_manager = BaseSessionManager(db)

    try:
        await session_manager.increment_request_count(session_id, request_id)
        return {"status": "success", "message": "Request count incremented"}
    except Exception as e:
        logger.error("Failed to increment request count", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to increment request count",
        )


async def _update_request_log_unified(
    request_id: str,
    response_content: str,
    agent_id: str,
    response_metadata: dict[str, Any] | None = None,
    processing_time_ms: int | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Update RequestLog for any API type."""
    try:
        from shared_models.models import RequestLog
        from sqlalchemy import update

        # Update the RequestLog with response content
        stmt = (
            update(RequestLog)
            .where(RequestLog.request_id == request_id)
            .values(
                response_content=response_content,
                response_metadata=response_metadata or {},
                agent_id=agent_id,
                processing_time_ms=processing_time_ms,
                completed_at=datetime.now(timezone.utc),
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
