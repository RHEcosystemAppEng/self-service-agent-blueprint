"""Communication strategy abstraction for eventing vs direct HTTP modes."""

import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from agent_service.schemas import SessionResponse
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from shared_clients import get_agent_client, get_integration_dispatcher_client
from shared_clients.stream_processor import LlamaStackStreamProcessor
from shared_models import CloudEventSender, configure_logging, get_enum_value
from shared_models.models import AgentResponse, NormalizedRequest
from sqlalchemy.ext.asyncio import AsyncSession

from .normalizer import RequestNormalizer

logger = configure_logging("request-manager")

# Global registry for response futures (event-driven approach)
_response_futures_registry: dict[str, Any] = {}


def resolve_response_future(request_id: str, response_data: Dict[str, Any]) -> None:
    """Resolve a waiting response future when event is received."""
    logger.info(
        "Attempting to resolve response future",
        request_id=request_id,
        registry_keys=list(_response_futures_registry.keys()),
    )

    if request_id in _response_futures_registry:
        future = _response_futures_registry[request_id]
        if not future.done():
            future.set_result(response_data)
            logger.info(
                "Response future resolved",
                request_id=request_id,
            )
        else:
            logger.debug(
                "Response future already resolved",
                request_id=request_id,
            )
    else:
        logger.warning(
            "No waiting response future found",
            request_id=request_id,
            available_futures=list(_response_futures_registry.keys()),
        )


async def create_or_get_session_shared(
    request: Any, db: AsyncSession
) -> Optional[SessionResponse]:
    """Shared session management logic for all communication strategies.

    This function handles the common pattern of:
    1. Looking for existing active sessions for the user
    2. Reusing existing sessions if found (updating timestamp)
    3. Creating new sessions if none found

    Args:
        request: The request object containing user_id, integration_type, etc.
        db: Database session for queries and updates

    Returns:
        SessionResponse object for the session (existing or newly created)
    """
    import uuid

    from agent_service.schemas import SessionResponse
    from shared_models.models import RequestSession, SessionStatus
    from sqlalchemy import select

    # Try to find existing active session
    stmt = (
        select(RequestSession)
        .where(
            RequestSession.user_id == request.user_id,
            RequestSession.integration_type == request.integration_type,
            RequestSession.status == SessionStatus.ACTIVE.value,
        )
        .order_by(RequestSession.last_request_at.desc())
    )

    result = await db.execute(stmt)
    existing_sessions = result.scalars().all()

    if existing_sessions:
        # Use the most recent session (first in the ordered list)
        existing_session = existing_sessions[0]

        # If we found multiple sessions, clean up the old ones
        if len(existing_sessions) > 1:
            logger.warning(
                "Multiple active sessions found for user, cleaning up old sessions",
                user_id=request.user_id,
                integration_type=request.integration_type,
                session_count=len(existing_sessions),
                selected_session_id=existing_session.session_id,
                all_session_ids=[s.session_id for s in existing_sessions],
            )

            # Use the cleanup utility function
            from .database_utils import cleanup_old_sessions

            deactivated_count = await cleanup_old_sessions(
                db=db,
                user_id=request.user_id,
                integration_type=request.integration_type,
                keep_recent_count=1,  # Keep only the most recent session
                max_age_hours=24,  # Deactivate sessions older than 24 hours
            )

            logger.info(
                "Session cleanup completed",
                user_id=request.user_id,
                deactivated_count=deactivated_count,
            )

        # Update activity timestamp
        existing_session.last_request_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        await db.commit()
        logger.info(
            "Reusing existing session",
            session_id=existing_session.session_id,
            current_agent_id=existing_session.current_agent_id,
            user_id=request.user_id,
        )
        return SessionResponse.model_validate(existing_session)

    # Create new session
    session = RequestSession(
        session_id=str(uuid.uuid4()),
        user_id=request.user_id,
        integration_type=request.integration_type,
        channel_id=getattr(request, "channel_id", None),
        thread_id=getattr(request, "thread_id", None),
        integration_metadata=request.metadata,
        status=SessionStatus.ACTIVE.value,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "Created new session",
        session_id=session.session_id,
        user_id=request.user_id,
    )
    return SessionResponse.model_validate(session)


class CommunicationStrategy(ABC):
    """Abstract base class for communication strategies."""

    async def create_or_get_session(
        self, request: Any, db: AsyncSession
    ) -> Optional[SessionResponse]:
        """Create or get session using shared session management logic.

        This method is implemented in the base class since all communication
        strategies use identical session management logic.
        """
        return await create_or_get_session_shared(request, db)

    @abstractmethod
    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """Send a request to the agent service."""
        pass

    @abstractmethod
    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver the response to the integration dispatcher."""
        pass


class EventingStrategy(CommunicationStrategy):
    """Communication strategy using Knative eventing."""

    def __init__(self) -> None:
        broker_url = os.getenv("BROKER_URL", "http://knative-broker:8080")
        self.event_sender = CloudEventSender(broker_url, "request-manager")

        # Configurable polling strategy
        self.poll_intervals = [
            float(x)
            for x in os.getenv("POLL_INTERVALS", "0.5,1.0,2.0,3.0,5.0").split(",")
        ]

    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """Send request via CloudEvent."""
        request_event_data = normalized_request.model_dump(mode="json")
        success = await self.event_sender.send_request_event(
            request_event_data,
            normalized_request.request_id,
            normalized_request.user_id,
            normalized_request.session_id,
        )

        if not success:
            logger.error("Failed to publish request event")
            return False

        logger.info(
            "Request sent via eventing",
            request_id=normalized_request.request_id,
            session_id=normalized_request.session_id,
        )
        return True

    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver response via CloudEvent."""
        response_event_data = agent_response.model_dump(mode="json")
        success = await self.event_sender.send_response_event(
            response_event_data,
            agent_response.request_id,
            agent_response.agent_id,
            agent_response.session_id,
        )

        if not success:
            logger.error("Failed to publish response event")
            return False

        logger.info(
            "Response delivered via eventing",
            request_id=agent_response.request_id,
            session_id=agent_response.session_id,
        )
        return True

    async def send_responses_request(self, request_data: Dict[str, Any]) -> bool:
        """Send responses request via CloudEvent."""
        success = await self.event_sender.send_responses_request_event(
            request_data,
            request_data.get("request_id"),
            request_data.get("user_id"),
            request_data.get("request_manager_session_id"),
        )

        if not success:
            logger.error("Failed to publish responses request event")
            return False

        logger.info(
            "Responses request sent via eventing",
            request_id=request_data.get("request_id"),
            session_id=request_data.get("request_manager_session_id"),
        )
        return True

    async def deliver_responses_response(self, response_data: Dict[str, Any]) -> bool:
        """Deliver responses response via CloudEvent."""
        success = await self.event_sender.send_responses_response_event(
            response_data,
            response_data.get("request_id") or "",
            response_data.get("agent_id"),
            response_data.get("session_id"),
        )

        if not success:
            logger.error("Failed to publish responses response event")
            return False

        logger.info(
            "Responses response delivered via eventing",
            request_id=response_data.get("request_id"),
            session_id=response_data.get("session_id"),
        )
        return True

    async def wait_for_response(self, request_id: str, timeout: int) -> Dict[str, Any]:
        """Wait for response event using event-driven approach."""
        logger.info(
            "Waiting for response event",
            request_id=request_id,
            timeout=timeout,
        )

        # Create a future that will be resolved when the response event is received
        response_future: asyncio.Future[Any] = asyncio.Future()

        # Store the future in the global registry so the event handler can resolve it
        _response_futures_registry[request_id] = response_future

        logger.info(
            "Response future registered",
            request_id=request_id,
            registry_keys=list(_response_futures_registry.keys()),
        )

        try:
            # Wait for the response event with timeout
            response_data = await asyncio.wait_for(response_future, timeout=timeout)

            logger.info(
                "Response event received",
                request_id=request_id,
            )

            return {
                "request_id": request_id,
                "session_id": response_data.get("session_id"),
                "status": "completed",
                "response": {
                    "content": response_data.get("content"),
                    "agent_id": response_data.get("agent_id"),
                    "metadata": response_data.get("metadata", {}),
                    "processing_time_ms": response_data.get("processing_time_ms"),
                    "requires_followup": response_data.get("requires_followup", False),
                    "followup_actions": response_data.get("followup_actions", []),
                },
            }

        except asyncio.TimeoutError:
            logger.error(
                "Timeout waiting for response event",
                request_id=request_id,
                timeout=timeout,
                registry_size=len(_response_futures_registry),
                active_requests=list(_response_futures_registry.keys()),
            )
            # Clean up the future on timeout
            if request_id in _response_futures_registry:
                del _response_futures_registry[request_id]
            raise Exception(f"Timeout waiting for response after {timeout} seconds")
        finally:
            # Clean up the future only if it wasn't resolved
            if request_id in _response_futures_registry:
                future = _response_futures_registry[request_id]
                if not future.done():
                    logger.debug(
                        "Cleaning up unresolved future",
                        request_id=request_id,
                    )
                    del _response_futures_registry[request_id]
                else:
                    logger.debug(
                        "Future was resolved, not cleaning up",
                        request_id=request_id,
                    )


class DirectHttpStrategy(CommunicationStrategy):
    """Communication strategy using direct HTTP calls."""

    def __init__(self) -> None:
        self.agent_client = get_agent_client()
        self.integration_client = get_integration_dispatcher_client()

    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """
        Send request via direct HTTP.

        Note: In direct HTTP mode, this method just validates the client is ready.
        The actual request processing happens synchronously in the main flow.
        """
        if not self.agent_client:
            logger.error("Agent client not initialized")
            return False

        logger.info(
            "Direct HTTP mode: Request will be processed synchronously",
            request_id=normalized_request.request_id,
            session_id=normalized_request.session_id,
        )
        return True  # Client is ready, request will be processed synchronously

    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver response via direct HTTP."""
        if not self.integration_client:
            logger.error("Integration client not initialized")
            return False

        success = await self.integration_client.deliver_response(
            agent_response.model_dump(mode="json")
        )

        if not success:
            logger.error("Failed to deliver response via direct HTTP")
            return False

        logger.info(
            "Response delivered via direct HTTP",
            request_id=agent_response.request_id,
            session_id=agent_response.session_id,
        )
        return True

    async def stream_response(
        self, agent_response: AgentResponse
    ) -> StreamingResponse | None:
        """Stream response using optimized streaming for direct HTTP mode."""
        if not self.integration_client:
            logger.error("Integration client not initialized")
            return None

        # Use optimized streaming for better performance
        async def generate_stream() -> AsyncGenerator[str, None]:
            try:
                # Stream start event
                yield LlamaStackStreamProcessor.create_sse_start_event(
                    agent_response.request_id
                )

                # Stream content with optimized performance
                async for (
                    chunk_data
                ) in LlamaStackStreamProcessor.stream_content_optimized(
                    agent_response.content,
                    content_type="content",
                ):
                    yield chunk_data

                # Stream completion event
                if (
                    agent_response.agent_id is None
                    or agent_response.processing_time_ms is None
                ):
                    logger.error(
                        "Cannot send completion event - missing agent_id or processing_time_ms",
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
                logger.error("Error in streaming response", error=str(e))
                yield LlamaStackStreamProcessor.create_sse_error_event(str(e))

        return LlamaStackStreamProcessor.create_sse_response(generate_stream())


def get_communication_strategy() -> CommunicationStrategy:
    """Get the appropriate communication strategy based on configuration."""
    eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"

    if eventing_enabled:
        return EventingStrategy()
    else:
        return DirectHttpStrategy()


async def check_communication_strategy() -> bool:
    """Check the health of the current communication strategy configuration."""
    try:
        eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"
        broker_url = os.getenv("BROKER_URL", "http://knative-broker:8080")

        if eventing_enabled:
            # In eventing mode, check if we can create a CloudEventSender
            # This works for both mock eventing and real Knative eventing
            from shared_models import CloudEventSender

            event_sender = CloudEventSender(broker_url, "request-manager")
            return event_sender is not None
        else:
            # In direct HTTP mode, check if we can reach the agent service
            from shared_clients import get_agent_client

            agent_client = get_agent_client()
            if not agent_client:
                return False

            try:
                response = await agent_client.get("/health", timeout=5.0)
                return response.status_code == 200
            except Exception:
                return False
    except Exception as e:
        logger.error("Communication strategy health check failed", error=str(e))
        return False


class UnifiedRequestProcessor:
    """Unified request processor that works with any communication strategy."""

    def __init__(
        self, strategy: CommunicationStrategy, agent_client: Any = None
    ) -> None:
        self.strategy = strategy
        self.agent_client = agent_client

    def _extract_session_data(self, session: Any) -> tuple[str, str]:
        """Extract session_id and current_agent_id from session data.

        Handles SessionResponse objects (from agent client) and SessionResponse objects (from session manager).
        """
        # Both agent client and session manager now return SessionResponse objects
        return session.session_id, session.current_agent_id

    async def process_request_async(
        self, request: Any, db: AsyncSession
    ) -> Dict[str, Any]:
        """Process a request asynchronously (eventing mode)."""
        logger.info(
            "Starting async request processing",
            user_id=request.user_id,
            request_type=request.request_type,
        )

        # Common request preparation
        normalized_request, session_id, current_agent_id = await self._prepare_request(
            request, db
        )

        # Send request using strategy
        logger.debug(
            "Sending request using strategy",
            request_id=normalized_request.request_id,
            session_id=session_id,
        )
        success = await self.strategy.send_request(normalized_request)

        if not success:
            logger.error(
                "Failed to send request",
                request_id=normalized_request.request_id,
                session_id=session_id,
            )
            raise Exception("Failed to send request")
        else:
            logger.debug(
                "Request sent successfully",
                request_id=normalized_request.request_id,
                session_id=session_id,
            )

        logger.info(
            "Request processed asynchronously",
            request_id=normalized_request.request_id,
            session_id=session_id,
            user_id=request.user_id,
            integration_type=get_enum_value(request.integration_type),
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session_id,
            "status": "accepted",
            "message": "Request has been queued for processing",
        }

    async def process_request_async_with_delivery(
        self, request: Any, db: AsyncSession, timeout: int = 120
    ) -> Dict[str, Any]:
        """Process a request asynchronously but deliver response in direct HTTP mode."""
        # Common request preparation
        normalized_request, session_id, current_agent_id = await self._prepare_request(
            request, db
        )

        # In direct HTTP mode, process synchronously but return immediately to avoid timeout
        if isinstance(self.strategy, DirectHttpStrategy):
            # Process the request in the background
            asyncio.create_task(
                self._process_and_deliver_background(normalized_request, db)
            )

            logger.info(
                "Request queued for background processing",
                request_id=normalized_request.request_id,
                session_id=session_id,
                user_id=request.user_id,
                integration_type=get_enum_value(request.integration_type),
            )

            return {
                "request_id": normalized_request.request_id,
                "session_id": session_id,
                "status": "accepted",
                "message": "Request has been queued for processing",
            }
        else:
            # Eventing mode - use standard async processing
            success = await self.strategy.send_request(normalized_request)

            if not success:
                raise Exception("Failed to send request")

            logger.info(
                "Request processed asynchronously",
                request_id=normalized_request.request_id,
                session_id=session_id,
                user_id=request.user_id,
                integration_type=get_enum_value(request.integration_type),
            )

            return {
                "request_id": normalized_request.request_id,
                "session_id": session_id,
                "status": "accepted",
                "message": "Request has been queued for processing",
            }

    async def _process_and_deliver_background(
        self, normalized_request: Any, db: AsyncSession
    ) -> None:
        """Process request in background and deliver response."""
        try:
            # Process the request
            agent_client = get_agent_client()
            if not agent_client:
                logger.error("Agent client not initialized for background processing")
                return

            # Note: Session management is now handled by the Agent Service automatically

            agent_response = await agent_client.process_request(normalized_request)
            if not agent_response:
                logger.error("Agent service failed to process request in background")
                return

            # Note: Request logging is now handled by the Agent Service

            # Deliver response via integration dispatcher
            delivery_success = await self.strategy.deliver_response(agent_response)
            if not delivery_success:
                logger.warning("Failed to deliver response in background")

            logger.info(
                "Background request processing completed",
                request_id=normalized_request.request_id,
                session_id=normalized_request.session_id,
                user_id=normalized_request.user_id,
            )

        except Exception as e:
            logger.error(
                "Error in background request processing",
                request_id=normalized_request.request_id,
                error=str(e),
            )

    async def process_request_sync(
        self, request: Any, db: AsyncSession, timeout: int = 120
    ) -> Dict[str, Any]:
        """Process a request synchronously and wait for response."""
        # Common request preparation
        normalized_request, session_id, current_agent_id = await self._prepare_request(
            request, db
        )

        # Handle different strategies
        if isinstance(self.strategy, EventingStrategy):
            # Eventing mode: send request and wait for response event
            logger.info(
                "Processing request in eventing mode",
                request_id=normalized_request.request_id,
            )

            # Send async request
            success = await self.strategy.send_request(normalized_request)
            if not success:
                raise Exception("Failed to send request")

            # Wait for response event instead of polling
            return await self.strategy.wait_for_response(
                normalized_request.request_id, timeout
            )

        elif isinstance(self.strategy, DirectHttpStrategy):
            # Direct HTTP mode: process synchronously
            agent_client = get_agent_client()
            if not agent_client:
                raise Exception("Agent client not initialized")

            # Note: Session management is now handled by the Agent Service automatically

            # Use streaming for better performance and user experience
            stream_response = await agent_client.process_request_stream(
                normalized_request
            )
            if not stream_response:
                raise Exception("Agent service failed to process request")

            # Process the streaming response to extract the final AgentResponse
            agent_response = await self._process_streaming_response(
                stream_response, normalized_request
            )
            if not agent_response:
                raise Exception("Failed to process streaming response")

            # NOTE: Agent routing is now handled by the Agent Service
            # No additional routing logic needed in Request Manager

            # Note: Request logging is now handled by the Agent Service

            # For sync requests, return response directly; for async requests, deliver via integration dispatcher
            if normalized_request.request_type.upper() != "SYNC":
                # Deliver response for async requests (Slack, email, etc.)
                delivery_success = await self.strategy.deliver_response(agent_response)
                if not delivery_success:
                    logger.warning("Failed to deliver response")

            # Prepare response data (always returned for sync requests)
            response_data = {
                "content": agent_response.content,
                "agent_id": agent_response.agent_id,
                "metadata": agent_response.metadata,
                "processing_time_ms": agent_response.processing_time_ms,
                "requires_followup": agent_response.requires_followup,
                "followup_actions": agent_response.followup_actions,
            }

        else:
            raise Exception("Unknown communication strategy")

        logger.info(
            "Request processed synchronously",
            request_id=normalized_request.request_id,
            session_id=session_id,
            user_id=request.user_id,
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session_id,
            "status": "completed",
            "response": response_data,
        }

    async def _process_streaming_response(
        self, stream_context_manager: Any, normalized_request: Any
    ) -> Optional[AgentResponse]:
        """Process a streaming response and extract the final AgentResponse."""
        import json

        from shared_models.models import AgentResponse

        try:
            content = ""
            agent_id = None
            processing_time_ms = None
            metadata: Dict[str, Any] = {}
            requires_followup = False
            followup_actions: list[Any] = []

            # Use the async context manager to get the response
            async with stream_context_manager as response:
                # Process the streaming response
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Remove "data: " prefix
                            event_type = data.get("type", "unknown")

                            if event_type == "content":
                                content += data.get("chunk", "")
                            elif event_type == "complete":
                                agent_id = data.get("agent_id")
                                processing_time_ms = data.get("processing_time_ms")
                            elif event_type == "error":
                                logger.error(
                                    "Streaming error", message=data.get("message")
                                )
                                return None
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse streaming data", line=line)
                            continue

            # Create AgentResponse from collected data
            if content and agent_id:
                return AgentResponse(
                    request_id=normalized_request.request_id,
                    session_id=normalized_request.session_id,
                    user_id=normalized_request.user_id,
                    agent_id=agent_id,
                    content=content,
                    metadata=metadata,
                    processing_time_ms=processing_time_ms,
                    requires_followup=requires_followup,
                    followup_actions=followup_actions,
                )
            else:
                logger.error(
                    "Incomplete streaming response",
                    content_length=len(content),
                    agent_id=agent_id,
                )
                return None

        except Exception as e:
            logger.error("Error processing streaming response", error=str(e))
            return None

    async def _prepare_request(
        self, request: Any, db: AsyncSession
    ) -> tuple[NormalizedRequest, str, str]:
        """Common request preparation logic: session management, normalization, and RequestLog creation.

        Returns:
            tuple: (normalized_request, session_id, current_agent_id)
        """
        normalizer = RequestNormalizer()

        # Delegate session management to the communication strategy
        logger.debug("Creating or getting session", user_id=request.user_id)
        session = await self.strategy.create_or_get_session(request, db)

        # Check if session creation failed
        if not session:
            logger.error("Failed to create or find session", user_id=request.user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session",
            )

        logger.info(
            "Session created/found successfully",
            session_id=session.session_id,
            user_id=request.user_id,
        )

        # Normalize the request
        session_id, current_agent_id = self._extract_session_data(session)
        normalized_request = normalizer.normalize_request(
            request, session_id, current_agent_id
        )

        # Create initial RequestLog entry for tracking
        await self._create_request_log_entry(normalized_request, db)

        return normalized_request, session_id, current_agent_id

    async def _create_request_log_entry(
        self, normalized_request: NormalizedRequest, db: AsyncSession
    ) -> None:
        """Create initial RequestLog entry for tracking."""
        from .database_utils import create_request_log_entry_unified

        await create_request_log_entry_unified(
            request_id=normalized_request.request_id,
            session_id=normalized_request.session_id,
            user_id=normalized_request.user_id,
            content=normalized_request.content,
            request_type=normalized_request.request_type,
            integration_type=normalized_request.integration_type,
            integration_context=normalized_request.integration_context,
            db=db,
        )
