"""Communication strategy abstraction for eventing mode."""

import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agent_service.schemas import SessionResponse
from fastapi import HTTPException, status
from shared_models import CloudEventSender, configure_logging
from shared_models.models import NormalizedRequest
from sqlalchemy.ext.asyncio import AsyncSession

from .normalizer import RequestNormalizer

logger = configure_logging("request-manager")

# Global registry for response futures (event-driven approach)
_response_futures_registry: dict[str, Any] = {}


def _should_filter_sessions_by_integration_type() -> bool:
    """Check if sessions should be filtered by integration type.

    Returns:
        True if sessions should be separated by integration type (legacy behavior)
        False if a single session should be maintained across all integration types (default)
    """
    return os.getenv("SESSION_PER_INTEGRATION_TYPE", "false").lower() == "true"


def _get_session_timeout_hours() -> int:
    """Get session timeout in hours from environment variable.

    Returns:
        Session timeout in hours (default: 336 hours = 2 weeks)
    """
    return int(os.getenv("SESSION_TIMEOUT_HOURS", "336"))


# Global polling task (single per pod)
_pod_polling_task: Optional[asyncio.Task[None]] = None


def get_pod_name() -> Optional[str]:
    """Get pod name from environment variable."""
    return os.getenv("HOSTNAME") or os.getenv("POD_NAME")


def resolve_response_future(request_id: str, response_data: Dict[str, Any]) -> bool:
    """Resolve a waiting response future when event is received.

    Note: This is now optional - the primary delivery mechanism is database polling.
    If a future exists and response arrives via event, resolve it immediately for speed.
    If not, the database polling will find it.

    Returns:
        True if future was found and resolved, False if not found (database polling will handle it)
    """
    logger.debug(
        "Attempting to resolve response future (optional - database polling is primary)",
        request_id=request_id,
        registry_keys=list(_response_futures_registry.keys()),
    )

    if request_id in _response_futures_registry:
        future = _response_futures_registry[request_id]
        if not future.done():
            # Mark as from event for logging
            response_data["_from_event"] = True
            future.set_result(response_data)
            logger.info(
                "Response future resolved via event (fast path)",
                request_id=request_id,
            )
            return True
        # Future already resolved, return True (no need to log - this is expected)
        return True
    else:
        # No future found - database polling will handle it
        logger.debug(
            "No waiting response future found - database polling will handle delivery",
            request_id=request_id,
        )
        return False


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

    # Resolve user_id to canonical user_id if it's an email address
    from shared_models import resolve_canonical_user_id
    from shared_models.models import RequestSession, SessionStatus
    from sqlalchemy import select

    canonical_user_id = await resolve_canonical_user_id(
        request.user_id,
        integration_type=getattr(request, "integration_type", None),
        db=db,
    )

    # Check if a session_id was provided in metadata (e.g., from X-Session-ID header in email reply, or thread metadata)
    # This allows integrations to provide a session_id to continue an existing session
    request_metadata = getattr(request, "metadata", {}) or {}
    provided_session_id = request_metadata.get("session_id")

    # If a session_id is provided, try to use it first
    if provided_session_id:
        logger.debug(
            "Session ID provided in request metadata, attempting to use it",
            provided_session_id=provided_session_id,
            canonical_user_id=canonical_user_id,
        )
        # Verify the provided session_id exists and belongs to this user
        stmt = select(RequestSession).where(
            RequestSession.session_id == provided_session_id,
            RequestSession.user_id == canonical_user_id,
            RequestSession.status == SessionStatus.ACTIVE.value,
        )
        result = await db.execute(stmt)
        provided_session = result.scalar_one_or_none()

        if provided_session:
            # Check if session is expired
            now = datetime.now(timezone.utc)
            if provided_session.expires_at is None or provided_session.expires_at > now:
                # Valid session found - update activity timestamp and return it
                provided_session.last_request_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                await db.commit()
                logger.info(
                    "Reusing provided session from metadata",
                    session_id=provided_session_id,
                    canonical_user_id=canonical_user_id,
                )
                return SessionResponse.model_validate(provided_session)
            else:
                logger.warning(
                    "Provided session_id is expired, will create new session",
                    session_id=provided_session_id,
                    canonical_user_id=canonical_user_id,
                )
        else:
            logger.warning(
                "Provided session_id not found or doesn't belong to user, will create new session",
                provided_session_id=provided_session_id,
                canonical_user_id=canonical_user_id,
            )

    # Check if we should filter by integration type
    filter_by_integration_type = _should_filter_sessions_by_integration_type()

    # Get current time for expiration checks
    now = datetime.now(timezone.utc)

    # Try to find existing active session (not expired)
    where_conditions = [
        RequestSession.user_id == canonical_user_id,
        RequestSession.status == SessionStatus.ACTIVE.value,
        # Filter out expired sessions
        ((RequestSession.expires_at.is_(None)) | (RequestSession.expires_at > now)),
    ]

    # Optionally filter by integration type based on env var
    if filter_by_integration_type:
        where_conditions.append(
            RequestSession.integration_type == request.integration_type
        )

    stmt = (
        select(RequestSession)
        .where(*where_conditions)
        .order_by(RequestSession.last_request_at.desc())
    )

    result = await db.execute(stmt)
    existing_sessions = result.scalars().all()

    # Debug logging for session lookup
    logger.debug(
        "Session lookup results",
        canonical_user_id=canonical_user_id,
        original_user_id=request.user_id,
        integration_type=(
            request.integration_type.value
            if hasattr(request.integration_type, "value")
            else str(request.integration_type)
        ),
        filter_by_integration_type=filter_by_integration_type,
        found_sessions_count=len(existing_sessions),
    )

    if existing_sessions:
        # Use the most recent session (first in the ordered list)
        existing_session = existing_sessions[0]

        # If we found multiple sessions, clean up the old ones
        if len(existing_sessions) > 1:
            logger.warning(
                "Multiple active sessions found for user, cleaning up old sessions",
                user_id=canonical_user_id,
                original_user_id=request.user_id,
                integration_type=request.integration_type,
                session_count=len(existing_sessions),
                selected_session_id=existing_session.session_id,
                all_session_ids=[s.session_id for s in existing_sessions],
                filter_by_integration_type=filter_by_integration_type,
            )

            # Use the cleanup utility function
            from shared_models import get_enum_value

            from .database_utils import cleanup_old_sessions

            # Pass integration_type only if filtering by it, otherwise None
            # Convert enum to string value for consistency
            cleanup_integration_type = (
                get_enum_value(request.integration_type)
                if filter_by_integration_type
                else None
            )

            deactivated_count = await cleanup_old_sessions(
                db=db,
                user_id=canonical_user_id,
                integration_type=cleanup_integration_type,
            )

            logger.info(
                "Session cleanup completed",
                user_id=canonical_user_id,
                original_user_id=request.user_id,
                deactivated_count=deactivated_count,
            )

        # Update activity timestamp
        existing_session.last_request_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        await db.commit()
        logger.info(
            "Reusing existing session",
            session_id=existing_session.session_id,
            current_agent_id=existing_session.current_agent_id,
            user_id=canonical_user_id,
            original_user_id=request.user_id,
            integration_type=(
                existing_session.integration_type.value
                if hasattr(existing_session.integration_type, "value")
                else str(existing_session.integration_type)
            ),
            filter_by_integration_type=filter_by_integration_type,
        )
        return SessionResponse.model_validate(existing_session)

    # Create new session with expiration
    from datetime import timedelta

    session_timeout_hours = _get_session_timeout_hours()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=session_timeout_hours)

    # Get integration_type from request, with fallback to None if not available
    # This handles cases where BaseRequest might have integration_type=None
    request_integration_type = getattr(request, "integration_type", None)

    session = RequestSession(
        session_id=str(uuid.uuid4()),
        user_id=canonical_user_id,
        integration_type=request_integration_type,
        channel_id=getattr(request, "channel_id", None),
        thread_id=getattr(request, "thread_id", None),
        integration_metadata=request.metadata,
        status=SessionStatus.ACTIVE.value,
        expires_at=expires_at,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "Created new session",
        session_id=session.session_id,
        user_id=canonical_user_id,
        original_user_id=request.user_id,
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
    async def wait_for_response(
        self, request_id: str, timeout: int, db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Wait for response from the agent service."""
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

    async def wait_for_response(
        self, request_id: str, timeout: int, db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Wait for response using single per-pod polling mechanism.

        Primary mechanism: Single background polling task per pod checks database.
        Any pod that receives the response event stores it in the database.

        Optional fast path: If response arrives via event at this pod, resolve immediately.
        """
        logger.info(
            "Waiting for response (single pod polling mechanism)",
            request_id=request_id,
            timeout=timeout,
        )

        # Create a future that can be resolved by either event or polling
        response_future: asyncio.Future[Any] = asyncio.Future()

        # Store the future in the global registry (for fast path via event and polling)
        _response_futures_registry[request_id] = response_future
        logger.debug(
            "Response future registered",
            request_id=request_id,
        )

        try:
            # Wait for the response (either from event fast path or single pod polling)
            response_data = await asyncio.wait_for(response_future, timeout=timeout)

            logger.info(
                "Response received",
                request_id=request_id,
                source="event" if response_data.get("_from_event") else "database",
            )

            # Remove internal flag
            response_data.pop("_from_event", None)

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
                "Timeout waiting for response",
                request_id=request_id,
                timeout=timeout,
            )
            raise Exception(f"Timeout waiting for response after {timeout} seconds")
        finally:
            # Clean up the future
            if request_id in _response_futures_registry:
                del _response_futures_registry[request_id]


async def _start_pod_polling_task(pod_name: str) -> None:
    """Start the single per-pod polling task that checks for responses.

    This task polls the database for responses where pod_name matches this pod
    and request_id is in the _response_futures_registry.
    """
    global _pod_polling_task

    if _pod_polling_task and not _pod_polling_task.done():
        logger.warning("Pod polling task already running")
        return

    _pod_polling_task = asyncio.create_task(_pod_response_poller(pod_name))
    logger.info(
        "Started single per-pod polling task",
        pod_name=pod_name,
    )


async def _pod_response_poller(pod_name: str) -> None:
    """Single background polling task per pod that checks for responses.

    This polls the database for all waiting request_ids where:
    - pod_name matches this pod
    - response_content is not null
    - request_id is in _response_futures_registry

    When a response is found, it resolves the corresponding future.
    """
    poll_interval = float(os.getenv("DB_POLL_INTERVAL", "0.5"))  # Poll every 500ms

    logger.info(
        "Pod response poller started",
        pod_name=pod_name,
        poll_interval=poll_interval,
    )

    while True:
        try:
            # Get all waiting request_ids from registry
            waiting_request_ids = list(_response_futures_registry.keys())

            if not waiting_request_ids:
                # No requests waiting, sleep and continue
                await asyncio.sleep(poll_interval)
                continue

            # Query database for responses where pod_name matches (or is NULL) and response_content is not null
            # Note: We check for NULL pod_name to handle cases where it wasn't set (e.g., older requests or CloudEvents)
            # Since we filter by request_id.in_(waiting_request_ids), we only check requests this pod is waiting for
            from shared_models import get_database_manager
            from shared_models.models import RequestLog
            from sqlalchemy import or_, select

            db_manager = get_database_manager()
            async with db_manager.get_session() as db:
                stmt = select(RequestLog).where(
                    RequestLog.request_id.in_(waiting_request_ids),
                    or_(
                        RequestLog.pod_name == pod_name,
                        RequestLog.pod_name.is_(
                            None
                        ),  # Handle requests without pod_name (e.g., CloudEvents)
                    ),
                    RequestLog.response_content.isnot(None),
                )
                result = await db.execute(stmt)
                request_logs = result.scalars().all()

                # Resolve futures for any found responses
                for request_log in request_logs:
                    request_id: str = str(request_log.request_id)
                    if request_id in _response_futures_registry:
                        future = _response_futures_registry[request_id]
                        if not future.done():
                            response_data: Dict[str, Any] = {
                                "request_id": request_id,
                                "session_id": request_log.session_id,
                                "agent_id": request_log.agent_id,
                                "content": request_log.response_content,
                                "metadata": request_log.response_metadata or {},
                                "processing_time_ms": request_log.processing_time_ms,
                                "requires_followup": False,
                                "followup_actions": [],
                                "_from_event": False,  # Flag to indicate source
                            }
                            future.set_result(response_data)
                            logger.info(
                                "Response found in database via single pod polling",
                                request_id=request_id,
                                pod_name=pod_name,
                            )

        except asyncio.CancelledError:
            logger.info("Pod polling task cancelled", pod_name=pod_name)
            break
        except Exception as e:
            logger.error(
                "Error in pod polling task",
                pod_name=pod_name,
                error=str(e),
            )
            # Continue polling even on error
            await asyncio.sleep(poll_interval)
        else:
            # Wait before next poll
            await asyncio.sleep(poll_interval)


def get_communication_strategy() -> CommunicationStrategy:
    """Get the communication strategy (eventing-based)."""
    return EventingStrategy()


async def check_communication_strategy() -> bool:
    """Check the health of the eventing communication strategy configuration."""
    try:
        broker_url = os.getenv("BROKER_URL", "http://knative-broker:8080")

        # Check if we can create a CloudEventSender
        # This works for both mock eventing and real Knative eventing
        from shared_models import CloudEventSender

        event_sender = CloudEventSender(broker_url, "request-manager")
        return event_sender is not None
    except Exception as e:
        logger.error("Communication strategy health check failed", error=str(e))
        return False


class UnifiedRequestProcessor:
    """Unified request processor for eventing-based communication."""

    def __init__(self, strategy: CommunicationStrategy) -> None:
        self.strategy = strategy

    def _extract_session_data(self, session: Any) -> tuple[str, str]:
        """Extract session_id and current_agent_id from session data.

        Handles SessionResponse objects (from agent client) and SessionResponse objects (from session manager).
        """
        # Both agent client and session manager now return SessionResponse objects
        return session.session_id, session.current_agent_id

    async def process_request_sync(
        self,
        request: Any,
        db: AsyncSession,
        timeout: int = 120,
        set_pod_name: bool = True,
    ) -> Dict[str, Any]:
        """Process a request synchronously and wait for response via eventing.

        Args:
            set_pod_name: If True, set pod_name for requests that wait for responses.
                         If False, don't set pod_name (e.g., CloudEvent requests).
        """
        # Common request preparation
        normalized_request, session_id, current_agent_id = await self._prepare_request(
            request, db, set_pod_name=set_pod_name
        )

        # Send request via eventing and wait for response event
        logger.info(
            "Processing request in eventing mode",
            request_id=normalized_request.request_id,
        )

        # Send async request
        success = await self.strategy.send_request(normalized_request)
        if not success:
            raise Exception("Failed to send request")

        # Wait for response event (with database polling fallback for 100% delivery)
        response = await self.strategy.wait_for_response(
            normalized_request.request_id, timeout, db
        )

        logger.info(
            "Request processed successfully",
            request_id=normalized_request.request_id,
            session_id=session_id,
            user_id=request.user_id,
        )

        return response

    async def _prepare_request(
        self, request: Any, db: AsyncSession, set_pod_name: bool = True
    ) -> tuple[NormalizedRequest, str, str]:
        """Common request preparation logic: session management, normalization, and RequestLog creation.

        Args:
            set_pod_name: If True, set pod_name for requests that wait for responses.
                         If False, don't set pod_name (e.g., CloudEvent requests).

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

        # For llama-stack and agent-service, we need to use email instead of canonical UUID
        # Look up user email from canonical user_id and replace in NormalizedRequest
        try:
            from shared_models.models import User
            from shared_models.user_utils import is_uuid
            from sqlalchemy import select

            # Only look up email if user_id is a UUID (canonical user_id)
            if is_uuid(normalized_request.user_id):
                stmt = select(User).where(User.user_id == normalized_request.user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if user and user.primary_email:
                    user_email = str(user.primary_email)
                    # Replace UUID with email for llama-stack/agent-service communication
                    normalized_request.user_id = user_email
                    logger.debug(
                        "Replaced canonical user_id with email for agent-service",
                        canonical_user_id=request.user_id,
                        user_email=user_email,
                    )
        except Exception as e:
            logger.warning(
                "Failed to retrieve user email for normalization",
                user_id=normalized_request.user_id,
                error=str(e),
            )

        # Create initial RequestLog entry for tracking
        await self._create_request_log_entry(
            normalized_request, db, set_pod_name=set_pod_name
        )

        return normalized_request, session_id, current_agent_id

    async def _create_request_log_entry(
        self,
        normalized_request: NormalizedRequest,
        db: AsyncSession,
        set_pod_name: bool = True,
    ) -> None:
        """Create initial RequestLog entry for tracking.

        Args:
            set_pod_name: If True, set pod_name for requests that wait for responses.
                         If False, don't set pod_name (e.g., CloudEvent requests).
        """
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
            set_pod_name=set_pod_name,
        )
