"""Main FastAPI application for Request Manager."""

import asyncio
import json

# Configure structured logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from shared_models import (
    CloudEventHandler,
    CloudEventSender,
    EventTypes,
    configure_logging,
    create_cloudevent_response,
    create_health_check_endpoint,
    create_shared_lifespan,
    get_db_session_dependency,
    parse_cloudevent_from_request,
)
from shared_models.models import ErrorResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tracing_config.auto_tracing import run as auto_tracing_run
from tracing_config.auto_tracing import (
    tracingIsActive,
)

from . import __version__
from .communication_strategy import (
    UnifiedRequestProcessor,
    check_communication_strategy,
    get_communication_strategy,
)
from .normalizer import RequestNormalizer
from .response_handler import UnifiedResponseHandler
from .schemas import (
    BaseRequest,
    CLIRequest,
    EmailRequest,
    HealthCheck,
    SlackRequest,
    ToolRequest,
    WebRequest,
    ZammadRequest,
)

# Configure structured logging and auto tracing
SERVICE_NAME = "request-manager"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)


async def _session_cleanup_task() -> None:
    """Background task to periodically clean up expired and inactive sessions."""
    import asyncio

    from shared_models import get_database_manager

    cleanup_interval_hours = int(os.getenv("SESSION_CLEANUP_INTERVAL_HOURS", "24"))
    cleanup_interval_seconds = cleanup_interval_hours * 3600
    inactive_session_retention_days = int(
        os.getenv("INACTIVE_SESSION_RETENTION_DAYS", "30")
    )

    logger.info(
        "Starting session cleanup task",
        cleanup_interval_hours=cleanup_interval_hours,
        inactive_session_retention_days=inactive_session_retention_days,
    )

    while True:
        try:
            await asyncio.sleep(cleanup_interval_seconds)

            db_manager = get_database_manager()
            async with db_manager.get_session() as db:
                from .database_utils import (
                    delete_inactive_sessions,
                    expire_old_sessions,
                )

                # First, expire sessions that have passed their expiration time
                expired_count = await expire_old_sessions(db)

                # Then, delete inactive sessions older than retention period
                deleted_count = await delete_inactive_sessions(
                    db, older_than_days=inactive_session_retention_days
                )

                if expired_count > 0 or deleted_count > 0:
                    logger.info(
                        "Session cleanup completed",
                        expired_count=expired_count,
                        deleted_count=deleted_count,
                    )

        except asyncio.CancelledError:
            logger.info("Session cleanup task cancelled")
            break
        except Exception as e:
            logger.error(
                "Error in session cleanup task",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue running even on error
            await asyncio.sleep(60)  # Wait 1 minute before retrying on error


async def _request_manager_startup() -> None:
    """Custom startup logic for Request Manager."""
    import asyncio

    # Initialize unified processor
    global unified_processor
    communication_strategy = get_communication_strategy()

    unified_processor = UnifiedRequestProcessor(communication_strategy)
    logger.info(
        "Initialized unified request processor",
        strategy_type=type(communication_strategy).__name__,
    )

    # Start single per-pod polling task
    from .communication_strategy import get_pod_name

    pod_name = get_pod_name()
    if pod_name:
        from .communication_strategy import _start_pod_polling_task

        await _start_pod_polling_task(pod_name)
        logger.info(
            "Started single per-pod polling task",
            pod_name=pod_name,
        )
    else:
        logger.warning(
            "Pod name not found in environment (HOSTNAME or POD_NAME) - single pod polling not started"
        )

    if pod_name:
        # Start pod heartbeat (for reclaim liveness)
        from .pod_heartbeat import run_pod_heartbeat_loop

        asyncio.create_task(run_pod_heartbeat_loop())

        # Start background reclaim (stuck processing across sessions)
        from .background_reclaim import run_background_reclaim_loop

        asyncio.create_task(run_background_reclaim_loop())

    # Start session cleanup background task
    asyncio.create_task(_session_cleanup_task())
    logger.info("Started session cleanup background task")


# Create lifespan using shared utility with custom startup
def lifespan(app: FastAPI) -> Any:
    return create_shared_lifespan(
        service_name="request-manager",
        version=__version__,
        custom_startup=_request_manager_startup,
    )


# Create FastAPI application
app = FastAPI(
    title="Self-Service Agent Request Manager",
    description="Request Management Layer for Self-Service Agent Blueprint",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
normalizer = RequestNormalizer()
security = HTTPBearer(auto_error=False)
unified_processor: Optional[UnifiedRequestProcessor] = None

# Security configuration
API_KEYS = {
    "snow-integration": os.getenv("SNOW_API_KEY", ""),
    "hr-system": os.getenv("HR_API_KEY", ""),
    "monitoring-system": os.getenv("MONITORING_API_KEY", ""),
}

# JWT Configuration
JWT_ENABLED = os.getenv("JWT_ENABLED", "false").lower() == "true"
JWT_ISSUERS = json.loads(os.getenv("JWT_ISSUERS", "[]"))
JWT_VALIDATION_CONFIG = {
    "verify_signature": os.getenv("JWT_VERIFY_SIGNATURE", "true").lower() == "true",
    "verify_expiration": os.getenv("JWT_VERIFY_EXPIRATION", "true").lower() == "true",
    "verify_audience": os.getenv("JWT_VERIFY_AUDIENCE", "true").lower() == "true",
    "verify_issuer": os.getenv("JWT_VERIFY_ISSUER", "true").lower() == "true",
    "leeway": int(os.getenv("JWT_LEEWAY", "60")),
}

# API Key Configuration
API_KEYS_ENABLED = os.getenv("API_KEYS_ENABLED", "true").lower() == "true"
WEB_API_KEYS = json.loads(os.getenv("WEB_API_KEYS", "{}"))


def verify_api_key(api_key: str, tool_id: Optional[str] = None) -> bool:
    """Verify API key for tool integrations."""
    if not api_key:
        return False

    # Check against configured API keys
    for key_name, key_value in API_KEYS.items():
        if key_value and api_key == key_value:
            # Optionally verify tool_id matches key_name
            if tool_id and tool_id not in key_name:
                continue
            return True

    return False


def verify_web_api_key(api_key: Optional[str]) -> Optional[str]:
    """Verify web API key and return associated user email."""
    if not API_KEYS_ENABLED or not api_key:
        return None

    api_key_value = WEB_API_KEYS.get(api_key)
    return str(api_key_value) if api_key_value is not None else None


async def validate_jwt_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Validate JWT token and return user information."""
    if not JWT_ENABLED or not token:
        return None

    try:
        # Decode token header to get algorithm
        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get("alg", "RS256")

        # Find matching issuer configuration
        issuer_config = None
        for issuer in JWT_ISSUERS:
            if algorithm in issuer.get("algorithms", ["RS256"]):
                issuer_config = issuer
                break

        if not issuer_config:
            logger.warning(
                "No matching issuer configuration found", algorithm=algorithm
            )
            return None

        # For now, skip signature verification if not configured
        # In production, you would fetch and verify the JWKS
        if not JWT_VALIDATION_CONFIG["verify_signature"]:
            payload = jwt.decode(
                token, options={"verify_signature": False}, algorithms=[algorithm]
            )
        else:
            # TODO: Implement proper JWKS fetching and signature verification
            logger.warning("JWT signature verification not yet implemented")
            payload = jwt.decode(
                token, options={"verify_signature": False}, algorithms=[algorithm]
            )

        # Validate issuer
        if JWT_VALIDATION_CONFIG["verify_issuer"]:
            if payload.get("iss") != issuer_config["issuer"]:
                logger.warning(
                    "JWT issuer mismatch",
                    expected=issuer_config["issuer"],
                    actual=payload.get("iss"),
                )
                return None

        # Validate audience
        if JWT_VALIDATION_CONFIG["verify_audience"]:
            audience = payload.get("aud")
            expected_audience = issuer_config.get("audience")
            if expected_audience and audience != expected_audience:
                logger.warning(
                    "JWT audience mismatch", expected=expected_audience, actual=audience
                )
                return None

        # Extract user information
        user_info = {
            "user_id": payload.get("sub")
            or payload.get("user_id")
            or payload.get("preferred_username"),
            "email": payload.get("email"),
            "groups": payload.get("groups", []),
            "token": token,
            "issuer": payload.get("iss"),
            "audience": payload.get("aud"),
        }

        if not user_info["user_id"]:
            logger.warning("No user ID found in JWT token")
            return None

        return user_info

    except InvalidTokenError as e:
        logger.warning("Invalid JWT token", error=str(e))
        return None
    except Exception as e:
        logger.error("JWT validation error", error=str(e))
        return None


async def get_current_user(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Dict[str, Any]]:
    """Extract and validate user information from JWT token or API key."""
    if not authorization or not authorization.credentials:
        return None

    token = authorization.credentials

    # Try JWT validation first
    if JWT_ENABLED:
        user_info = await validate_jwt_token(token)
        if user_info:
            logger.info("User authenticated via JWT", user_id=user_info.get("user_id"))
            return user_info

    # Fallback to API key validation
    if API_KEYS_ENABLED:
        user_email = verify_web_api_key(token)
        if user_email:
            user_info = {
                "user_id": token,  # Use API key as user ID
                "email": user_email,
                "groups": [],
                "token": token,
                "auth_method": "api_key",
            }
            logger.info(
                "User authenticated via API key", user_id=token, email=user_email
            )
            return user_info

    # Legacy: Check for user headers (from JWT or other auth systems)
    # This is kept for backward compatibility with legacy deployments
    user_info = {}
    user_id = (
        request.headers.get("x-user-id")
        or request.headers.get("x-forwarded-user")
        or request.headers.get("x-remote-user")
    )

    if user_id:
        user_info["user_id"] = user_id
        user_info["email"] = request.headers.get("x-user-email")
        user_info["groups"] = (
            request.headers.get("x-user-groups", "").split(",")
            if request.headers.get("x-user-groups")
            else []
        )
        user_info["token"] = token
        user_info["auth_method"] = "legacy_headers"
        logger.info("User authenticated via legacy headers", user_id=user_id)
        return user_info

    logger.warning("No valid authentication method found")
    return None


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint - lightweight without database dependency."""
    return {
        "status": "healthy",
        "service": "request-manager",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/detailed", response_model=HealthCheck)
async def detailed_health_check(
    db: AsyncSession = Depends(get_db_session_dependency),
) -> HealthCheck:
    """Detailed health check with database dependency for monitoring."""
    result = await create_health_check_endpoint(
        service_name="request-manager",
        version=__version__,
        db=db,
        additional_checks={"communication_strategy": check_communication_strategy},
    )

    return HealthCheck(
        status=result["status"],
        database_connected=result["database_connected"],
        services=result["services"],
    )


@app.post("/api/v1/requests/web")
async def handle_web_request(
    web_request: WebRequest,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Handle web interface requests with JWT authentication."""
    # Validate user authentication for web requests
    if not current_user or not current_user.get("user_id"):
        logger.warning("Unauthenticated web request", request_user=web_request.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    # Ensure the authenticated user matches the request user
    if current_user["user_id"] != web_request.user_id:
        logger.warning(
            "User ID mismatch",
            authenticated_user=current_user["user_id"],
            request_user=web_request.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch"
        )

    return await _process_request_adaptive(web_request, db)


@app.post("/api/v1/requests/cli")
async def handle_cli_request(
    cli_request: CLIRequest,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Handle CLI requests with authentication."""
    # Validate user authentication for CLI requests
    if not current_user or not current_user.get("user_id"):
        logger.warning("Unauthenticated CLI request", request_user=cli_request.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    # Ensure the authenticated user matches the request user
    if current_user["user_id"] != cli_request.user_id:
        logger.warning(
            "User ID mismatch",
            authenticated_user=current_user["user_id"],
            request_user=cli_request.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch"
        )

    return await _process_request_adaptive(cli_request, db)


@app.post("/api/v1/requests/tool")
async def handle_tool_request(
    tool_request: ToolRequest,
    db: AsyncSession = Depends(get_db_session_dependency),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
) -> Dict[str, Any]:
    """Handle tool-generated requests with API key authentication."""
    # Verify API key for tool requests
    if not verify_api_key(x_api_key or "", tool_request.tool_id):
        logger.warning("Invalid API key for tool request", tool_id=tool_request.tool_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return await _process_request_adaptive(tool_request, db)


@app.post("/api/v1/requests/generic")
async def handle_generic_request(
    request: BaseRequest,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Handle generic requests."""
    return await _process_request_adaptive(request, db)


@app.post("/api/v1/events/cloudevents")
async def handle_cloudevent(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Handle incoming CloudEvents (e.g., from agent responses)."""
    try:
        # Parse CloudEvent from request using shared utility
        event_data = await parse_cloudevent_from_request(request)

        event_id = event_data.get("id")
        event_type = event_data.get("type")
        event_source = event_data.get("source")

        logger.info(
            "CloudEvent received",
            event_id=event_id,
            event_type=event_type,
            event_source=event_source,
        )

        # Validate required CloudEvent fields (type and source are required per spec)
        if not event_type or not event_source:
            logger.warning(
                "CloudEvent missing required fields",
                event_id=event_id,
                has_type=bool(event_type),
                has_source=bool(event_source),
            )
            return await create_cloudevent_response(
                status="error",
                message="CloudEvent missing required fields (type, source)",
                details={"event_id": event_id},
            )

        # ✅ CIRCUIT BREAKER: Prevent feedback loops by ignoring self-generated events
        # Exception: Allow session events from request-manager (we send them to ourselves)
        if (
            "request-manager" in event_source or event_source == "request-manager"
        ) and event_type not in [
            EventTypes.SESSION_CREATE_OR_GET,
            EventTypes.SESSION_READY,
        ]:
            logger.info(
                "Ignoring self-generated event to prevent feedback loop",
                event_id=event_id,
                event_type=event_type,
                event_source=event_source,
            )
            return {"status": "ignored", "reason": "self-generated event"}

        # ✅ ATOMIC EVENT CLAIMING: Use check-and-set pattern to prevent duplicate processing
        # This provides 100% guarantee - only one pod can claim and process an event
        if event_id:
            from .database_utils import try_claim_event_for_processing

            event_claimed = await try_claim_event_for_processing(
                db,
                event_id,
                event_type,
                event_source,
                "request-manager",
            )

            if not event_claimed:
                logger.info(
                    "Event already claimed by another pod - skipping duplicate",
                    event_id=event_id,
                    event_type=event_type,
                    event_source=event_source,
                )
                return {
                    "status": "skipped",
                    "reason": "duplicate event (already claimed by another pod)",
                    "event_id": event_id,
                }

        # Handle session create-or-get events
        if event_type == EventTypes.SESSION_CREATE_OR_GET:
            from .session_events import _handle_session_create_or_get_event

            return await _handle_session_create_or_get_event(event_data, db)

        # Handle session ready events
        if event_type == EventTypes.SESSION_READY:
            from .session_events import _handle_session_ready_event

            return await _handle_session_ready_event(event_data, db)

        # Handle request created events (from integration dispatcher)
        if event_type == EventTypes.REQUEST_CREATED:
            return await _handle_request_created_event_from_data(event_data, db)

        # Handle agent response events
        if event_type == EventTypes.AGENT_RESPONSE_READY:
            # Use the already parsed event data from shared utility
            return await _handle_agent_response_event_from_data(event_data, db)

        logger.warning("Unhandled CloudEvent type", event_type=event_type)
        return await create_cloudevent_response(
            status="ignored",
            message="Unhandled event type",
            details={"event_type": event_type},
        )

    except Exception as e:
        logger.error("Failed to handle CloudEvent", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


async def _process_request_adaptive(
    request: Union[
        BaseRequest, SlackRequest, WebRequest, CLIRequest, EmailRequest, ToolRequest
    ],
    db: AsyncSession,
    timeout: int = int(os.getenv("AGENT_TIMEOUT", "120")),
) -> Dict[str, Any]:
    """Process a request synchronously and return the actual AI response.

    All user-facing and system-facing endpoints (web, CLI, Slack, tool, generic)
    should return immediate responses. All use the same flow: accept → wait for turn
    → process one → return. CloudEvent requests from integration-dispatcher follow
    the same path; responses are delivered via DB polling (any pod can process).
    """
    if not unified_processor:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified processor not initialized",
        )

    try:
        # Use unified processor for all requests (eventing-based communication)
        return await unified_processor.process_request_sync(request, db, timeout)
    except Exception as e:
        from .exceptions import RequestLogCreationError, SessionLockTimeoutError

        if isinstance(e, (RequestLogCreationError, SessionLockTimeoutError)):
            try:
                from .session_metrics import (
                    record_lock_timeout,
                    record_request_log_creation_failure,
                )

                if isinstance(e, RequestLogCreationError):
                    record_request_log_creation_failure()
                else:
                    record_lock_timeout()
            except Exception:  # noqa: BLE001
                pass
            logger.warning(
                "Request failed - service unavailable",
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. Please try again.",
            ) from e

        # Agent response timeout → 503 for retry (asyncio.TimeoutError from wait_for)
        def _is_timeout(exc: BaseException) -> bool:
            check: BaseException | None = exc
            while check:
                if isinstance(check, (TimeoutError, asyncio.TimeoutError)):
                    return True
                check = getattr(check, "__cause__", None) or getattr(
                    check, "__context__", None
                )
            return False

        if _is_timeout(e):
            logger.warning(
                "Request failed - agent response timeout",
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. Please try again.",
            ) from e

        # Transient DB errors (connection closed, invalid transaction) → 503 for retry
        def _is_transient_db_error(exc: BaseException) -> bool:
            s = str(exc).lower()
            if "connection" in s and ("closed" in s or "does not exist" in s):
                return True
            if "invalid transaction" in s and "rollback" in s:
                return True
            return False

        exc_check: BaseException | None = e
        while exc_check:
            if _is_transient_db_error(exc_check):
                break
            exc_check = getattr(exc_check, "__cause__", None)
        else:
            exc_check = None
        if exc_check is not None:
            logger.warning(
                "Request failed - transient DB error (retry)",
                error=str(exc_check),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. Please try again.",
            ) from e
        err_msg = str(e) or f"{type(e).__name__}: {repr(e)}"
        logger.error(
            "Failed to process request",
            error=err_msg,
            exc_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        ) from e


async def _handle_request_created_event_from_data(
    event_data: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """Handle request created CloudEvent from integration dispatcher."""
    from shared_models.cloudevent_utils import CloudEventHandler
    from shared_models.models import IntegrationType

    # Extract event metadata
    event_id = event_data.get("id")

    try:
        # Extract request data from CloudEvent
        request_data = CloudEventHandler.extract_event_data(event_data)

        # Convert to appropriate request schema based on integration_type
        integration_type_str = request_data.get("integration_type")
        if not integration_type_str:
            logger.error("Missing integration_type in request event data")
            return await create_cloudevent_response(
                status="error",
                message="Missing integration_type",
                details={"event_id": event_id},
            )

        integration_type = IntegrationType(integration_type_str.upper())

        # Validate required fields
        user_id = request_data.get("user_id")
        content = request_data.get("content")
        if not user_id or not content:
            logger.error(
                "Missing required fields in request event data",
                user_id=bool(user_id),
                content=bool(content),
            )
            return await create_cloudevent_response(
                status="error",
                message="Missing required fields (user_id, content)",
                details={"event_id": event_id},
            )

        # Extract session_id if provided (e.g., from X-Session-ID header in email reply, or thread metadata in Slack)
        # This allows integrations to provide a session_id to continue an existing session
        provided_session_id = request_data.get("session_id")
        metadata: Dict[str, Any] = dict(request_data.get("metadata") or {})
        if provided_session_id:
            metadata["session_id"] = provided_session_id
        # Pass request_id from integration-dispatcher (Slack: slack-{event_id}, Email: email-{message_id})
        # for deterministic event_id and dedup; normalizer will use it when present
        if request_data.get("request_id"):
            metadata["request_id"] = request_data["request_id"]

        if provided_session_id:
            logger.info(
                "Found session_id in request data, will attempt to reuse session",
                session_id=provided_session_id,
                integration_type=integration_type_str,
                user_id=user_id,
            )
        else:
            logger.debug(
                "No session_id provided in request data, will create or find session by user_id",
                integration_type=integration_type_str,
                user_id=user_id,
                request_data_keys=list(request_data.keys()),
            )

        # Extract common base fields
        base_fields: Dict[str, Any] = {
            "user_id": str(user_id),
            "content": str(content),
            "integration_type": integration_type,
            "metadata": metadata,
        }

        # Create request object based on integration type
        request: Union[SlackRequest, EmailRequest, ZammadRequest]
        if integration_type == IntegrationType.SLACK:
            slack_user_id = request_data.get("slack_user_id") or user_id
            slack_team_id = request_data.get("slack_team_id", "")
            if not isinstance(slack_user_id, str) or not isinstance(slack_team_id, str):
                logger.error("Invalid Slack fields in request event data")
                return await create_cloudevent_response(
                    status="error",
                    message="Invalid Slack fields",
                    details={"event_id": event_id},
                )
            request = SlackRequest(
                **base_fields,
                request_type=request_data.get("request_type", "slack_interaction"),
                channel_id=request_data.get("channel_id"),
                thread_id=request_data.get("thread_id"),
                slack_user_id=slack_user_id,
                slack_team_id=slack_team_id,
            )
        elif integration_type == IntegrationType.EMAIL:
            request = EmailRequest(
                **base_fields,
                request_type=request_data.get("request_type", "email_interaction"),
                email_from=request_data.get("email_from"),
                email_subject=request_data.get("email_subject"),
                email_message_id=request_data.get("email_message_id"),
                email_in_reply_to=request_data.get("email_in_reply_to"),
                email_references=request_data.get("email_references"),
            )
        elif integration_type == IntegrationType.ZAMMAD:
            ticket_id = request_data.get("ticket_id")
            article_id = request_data.get("article_id")
            group_id = request_data.get("group_id")
            zammad_delivery_id = request_data.get("zammad_delivery_id")
            created_by_id = request_data.get("created_by_id")
            if (
                ticket_id is None
                or article_id is None
                or group_id is None
                or not zammad_delivery_id
                or created_by_id is None
            ):
                logger.error(
                    "Missing required Zammad fields in request event data",
                    ticket_id=ticket_id,
                    article_id=article_id,
                    group_id=group_id,
                    zammad_delivery_id=bool(zammad_delivery_id),
                    created_by_id=created_by_id,
                )
                return await create_cloudevent_response(
                    status="error",
                    message="Missing required Zammad fields (ticket_id, article_id, group_id, zammad_delivery_id, created_by_id)",
                    details={"event_id": event_id},
                )
            request = ZammadRequest(
                **base_fields,
                request_type=request_data.get("request_type", "zammad_ticket_article"),
                ticket_id=int(ticket_id),
                article_id=int(article_id),
                group_id=int(group_id),
                group_name=request_data.get("group_name"),
                owner_id=request_data.get("owner_id"),
                created_by_id=int(created_by_id),
                zammad_delivery_id=str(zammad_delivery_id),
            )
        else:
            logger.warning(
                "Unsupported integration type in request event",
                integration_type=integration_type_str,
                event_id=event_id,
            )
            return await create_cloudevent_response(
                status="ignored",
                message="Unsupported integration type",
                details={
                    "integration_type": integration_type_str,
                    "event_id": event_id,
                },
            )

        # Process the request using the existing adaptive processor
        logger.info(
            "Processing request from CloudEvent",
            integration_type=integration_type_str,
            user_id=request.user_id,
            event_id=event_id,
        )

        result = await _process_request_adaptive(request, db)

        # Record successful event processing to prevent duplicate processing
        # This is critical for preventing race conditions when multiple pods receive the same event
        if event_id:
            from shared_models import EventTypes

            from .database_utils import record_processed_event

            await record_processed_event(
                db,
                event_id,
                EventTypes.REQUEST_CREATED,
                event_data.get("source", "integration-dispatcher"),
                result.get("request_id") if isinstance(result, dict) else None,
                result.get("session_id") if isinstance(result, dict) else None,
                "request-manager",
                "success",
            )

        # Forward response to Integration Dispatcher when response came via polling path
        # (Event path handles forwarding when a pod receives AGENT_RESPONSE_READY; this pod
        # got the response via DB polling and may never receive the event. Use try_claim to
        # ensure only one path forwards—whoever claims AGENT_RESPONSE_READY first does the forward.)
        # Use namespaced event_id (agent-response:{request_id}) to match create_response_event.
        if isinstance(result, dict) and result.get("status") == "completed":
            req_id = result.get("request_id")
            if req_id:
                from shared_models import EventTypes, agent_response_event_id

                from .database_utils import try_claim_event_for_processing

                agent_resp_event_id = agent_response_event_id(req_id)
                claimed = await try_claim_event_for_processing(
                    db,
                    agent_resp_event_id,
                    EventTypes.AGENT_RESPONSE_READY,
                    "agent-service",
                    "request-manager",
                )
                if claimed:
                    response_data = result.get("response") or {}
                    forward_event_data = {
                        "request_id": req_id,
                        "session_id": result.get("session_id"),
                        "user_id": request.user_id,
                        "content": response_data.get("content"),
                        "agent_id": response_data.get("agent_id"),
                        "created_at": result.get("created_at"),
                        "agent_received_at": result.get("agent_received_at"),
                        "metadata": response_data.get("metadata", {}),
                    }
                    logger.info(
                        "Forwarding response to Integration Dispatcher (polling path)",
                        request_id=req_id,
                        session_id=result.get("session_id"),
                    )
                    await _forward_response_to_integration_dispatcher(
                        forward_event_data, is_routing_response=False
                    )
                    from .database_utils import record_processed_event

                    await record_processed_event(
                        db,
                        agent_resp_event_id,
                        EventTypes.AGENT_RESPONSE_READY,
                        "agent-service",
                        req_id,
                        result.get("session_id"),
                        "request-manager",
                        "success",
                    )

        return result

    except Exception as e:
        logger.error(
            "Failed to handle request created event",
            event_id=event_id,
            error=str(e),
            exc_info=True,
        )

        # Record failed event processing
        if event_id:
            from shared_models import EventTypes

            from .database_utils import record_processed_event

            await record_processed_event(
                db,
                event_id,
                EventTypes.REQUEST_CREATED,
                event_data.get("source", "integration-dispatcher"),
                None,  # request_id unknown on error
                None,  # session_id unknown on error
                "request-manager",
                "error",
                str(e),
            )

        return await create_cloudevent_response(
            status="error",
            message="Failed to process request event",
            details={"event_id": event_id, "error": str(e)},
        )


async def _handle_agent_response_event_from_data(
    event_data: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """Handle agent response CloudEvent using unified response handler with pre-parsed data."""

    # Extract event metadata using common utility
    event_id, event_type, event_source = CloudEventHandler.get_event_metadata(
        event_data
    )

    try:
        # Extract response data using common utility
        response_data = CloudEventHandler.extract_event_data(event_data)
        request_id, session_id, agent_id, content, user_id = (
            CloudEventHandler.extract_response_data(response_data)
        )

        # Log session_id presence for debugging
        logger.info(
            "Extracted response data from CloudEvent",
            request_id=request_id,
            session_id=session_id,
            has_session_id_in_response_data=bool(response_data.get("session_id")),
            response_data_keys=list(response_data.keys()),
        )

        # Merge agent_received_at into metadata so it gets stored in response_metadata
        metadata = dict(response_data.get("metadata") or {})
        if response_data.get("agent_received_at"):
            metadata["agent_received_at"] = response_data.get("agent_received_at")

        # Use unified response handler (payload is in response_data = event_data["data"])
        response_handler = UnifiedResponseHandler(db)
        result = await response_handler.process_agent_response(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            content=content,
            metadata=metadata,
            processing_time_ms=response_data.get("processing_time_ms"),
            requires_followup=response_data.get("requires_followup", False),
            followup_actions=response_data.get("followup_actions", []),
        )

        # Fetch RequestLog for created_at (response ordering, API and forward payload)
        created_at_iso: Optional[str] = None
        from shared_models.models import RequestLog
        from sqlalchemy import select

        req_log_stmt = select(RequestLog).where(RequestLog.request_id == request_id)
        req_log_result = await db.execute(req_log_stmt)
        req_log = req_log_result.scalar_one_or_none()
        if req_log and req_log.created_at:
            created_at_iso = req_log.created_at.isoformat()

        # Resolve any waiting response futures for this request (fast path)
        # Note: If pod_name is NULL, ANY pod that receives the response event can immediately
        # process it if it has a waiting future. This provides the fastest possible response.
        # If no future found (wrong pod or no waiting request), response is still stored in database
        # and will be picked up by database polling in wait_for_response
        try:
            from request_manager.communication_strategy import resolve_response_future
            from request_manager.response_builder import (
                build_response_data_from_event_data,
            )

            complete_response_data = build_response_data_from_event_data(
                response_data, created_at_iso=created_at_iso
            )

            future_resolved = resolve_response_future(
                request_id, complete_response_data
            )
            if future_resolved:
                logger.info(
                    "Response future resolved via event (fast path)",
                    request_id=request_id,
                )
            else:
                # No waiting future found - response is stored in database
                # The correct pod's polling will find it (or any pod if pod_name is NULL)
                logger.debug(
                    "No waiting response future found - response stored in database, will be picked up by polling",
                    request_id=request_id,
                )
        except Exception as e:
            logger.debug(
                "Error resolving response future",
                request_id=request_id,
                error=str(e),
            )

        # Only forward response to Integration Dispatcher if it was actually processed
        if result.get("status") == "processed":
            # Ensure response_data has session_id and created_at before forwarding
            if "session_id" not in response_data:
                response_data["session_id"] = session_id
                logger.warning(
                    "Added missing session_id to response_data before forwarding",
                    request_id=request_id,
                    session_id=session_id,
                )
            if created_at_iso is not None:
                response_data["created_at"] = created_at_iso
            if response_data.get("agent_received_at") is None and metadata.get(
                "agent_received_at"
            ):
                response_data["agent_received_at"] = metadata["agent_received_at"]
            logger.info(
                "Forwarding response to Integration Dispatcher",
                request_id=request_id,
                session_id=response_data.get("session_id"),
                has_session_id=bool(response_data.get("session_id")),
            )
            await _forward_response_to_integration_dispatcher(
                response_data, result.get("routed_agent") is not None
            )
        else:
            logger.info(
                "Skipping Integration Dispatcher forwarding for duplicate response",
                request_id=request_id,
                status=result.get("status"),
                reason=result.get("reason"),
            )

        logger.info(
            "Agent response received and processed",
            request_id=request_id,
            session_id=session_id,
            agent_id=agent_id,
            status=result.get("status"),
        )

        # Record successful event processing
        from .database_utils import record_processed_event

        await record_processed_event(
            db,
            event_id,
            event_type,
            event_source,
            request_id,
            session_id,
            "request-manager",
            "success",
        )

        return {"status": "processed", "request_id": request_id}

    except Exception as e:
        logger.error("Failed to handle agent response event", error=str(e))

        # Record failed event processing
        from .database_utils import record_processed_event

        await record_processed_event(
            db,
            event_id,
            event_type,
            event_source,
            response_data.get("request_id") if "response_data" in locals() else None,
            response_data.get("session_id") if "response_data" in locals() else None,
            "request-manager",
            "error",
            str(e),
        )
        raise


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(  # type: ignore
            error=exc.detail,
            error_code=f"HTTP_{exc.status_code}",
        ).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error("Unhandled exception", error=str(exc), path=str(request.url))

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(  # type: ignore
            error="Internal server error",
            error_code="INTERNAL_ERROR",
        ).model_dump(mode="json"),
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "request_manager.main:app",
        host=host,
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
    )


async def _forward_response_to_integration_dispatcher(
    event_data: Dict[str, Any], is_routing_response: bool
) -> bool:
    """Forward agent response to Integration Dispatcher for delivery to user."""
    try:
        # Don't forward pure routing responses (just agent names) to users
        if is_routing_response:
            logger.info(
                "Skipping delivery of routing response to user",
                request_id=event_data.get("request_id"),
                agent_id=event_data.get("agent_id"),
                routing_response=event_data.get("content", "").strip(),
            )
            return True  # Success, but intentionally not delivered

        # Send response event for Integration Dispatcher to deliver
        broker_url = os.getenv("BROKER_URL", "http://knative-broker:8080")
        event_sender = CloudEventSender(broker_url, "request-manager")

        # Get original request context from database to include slack_user_id and email threading
        template_variables = event_data.get("template_variables", {})
        request_id = event_data.get("request_id")
        email_message_id = None
        email_in_reply_to = None
        email_references = None

        if request_id:
            # Retrieve original request context from RequestLog
            # Get database session
            from shared_models import resolve_canonical_user_id
            from shared_models.database import get_database_manager
            from shared_models.models import (
                IntegrationType,
                RequestLog,
                UserIntegrationMapping,
            )
            from sqlalchemy import select

            db_manager = get_database_manager()

            async with db_manager.get_session() as db:
                stmt = select(RequestLog).where(RequestLog.request_id == request_id)
                result = await db.execute(stmt)
                request_log = result.scalar_one_or_none()

                if request_log and request_log.normalized_request:
                    integration_context = request_log.normalized_request.get(
                        "integration_context", {}
                    )
                    slack_user_id = integration_context.get("slack_user_id")
                    slack_channel = integration_context.get("channel_id")
                    email_from = integration_context.get("email_from")

                    logger.info(
                        "Retrieved integration context from database",
                        request_id=request_id,
                        integration_context=integration_context,
                        slack_user_id=slack_user_id,
                        slack_channel=slack_channel,
                        email_from=email_from,
                    )

                    # If no slack_user_id in context, try to look it up from user mappings
                    if not slack_user_id:
                        # Resolve user_id to canonical user_id if needed
                        user_id_from_event = event_data.get("user_id")
                        if user_id_from_event:
                            canonical_user_id = await resolve_canonical_user_id(
                                user_id_from_event,
                                integration_type=None,
                                db=db,
                            )

                            # Look up Slack mapping for this canonical user_id
                            stmt = select(UserIntegrationMapping).where(
                                UserIntegrationMapping.user_id == canonical_user_id,
                                UserIntegrationMapping.integration_type
                                == IntegrationType.SLACK,
                            )
                            result = await db.execute(stmt)
                            slack_mapping = result.scalar_one_or_none()

                            if slack_mapping:
                                slack_user_id = slack_mapping.integration_user_id
                                logger.info(
                                    "Found Slack user_id from user mapping",
                                    request_id=request_id,
                                    canonical_user_id=canonical_user_id,
                                    slack_user_id=slack_user_id,
                                )

                    if slack_user_id:
                        template_variables["slack_user_id"] = slack_user_id
                        logger.info(
                            "Added slack_user_id to template variables",
                            request_id=request_id,
                            slack_user_id=slack_user_id,
                        )
                    else:
                        logger.warning(
                            "No slack_user_id found in integration context or user mappings",
                            request_id=request_id,
                            integration_context=integration_context,
                        )

                    if slack_channel:
                        template_variables["slack_channel"] = slack_channel
                        logger.debug(
                            "Added slack_channel to template variables",
                            request_id=request_id,
                            slack_channel=slack_channel,
                        )

                    if email_from:
                        template_variables["email_from"] = email_from
                        logger.info(
                            "Added email_from to template variables",
                            request_id=request_id,
                            email_from=email_from,
                        )

                    # Preserve email threading (RFC 5322) so reply stays in same thread
                    email_message_id = integration_context.get("email_message_id")
                    email_in_reply_to = integration_context.get("email_in_reply_to")
                    email_references = integration_context.get("email_references")
                    if email_message_id or email_in_reply_to or email_references:
                        logger.info(
                            "Including email thread headers for reply",
                            request_id=request_id,
                            has_message_id=bool(email_message_id),
                            has_in_reply_to=bool(email_in_reply_to),
                            has_references=bool(email_references),
                        )

        # Create delivery event data for Integration Dispatcher
        # This matches the structure expected by DeliveryRequest in Integration Dispatcher
        delivery_event_data = {
            "request_id": event_data.get("request_id"),
            "session_id": event_data.get("session_id"),
            "user_id": event_data.get("user_id"),
            "subject": event_data.get(
                "subject"
            ),  # This may be None for Agent Service events
            "content": event_data.get("content"),
            "template_variables": template_variables,
            "agent_id": event_data.get("agent_id"),
            "created_at": event_data.get("created_at"),
        }
        # Add email thread fields when present (non-empty) so integration-dispatcher can set In-Reply-To/References
        if email_message_id:
            delivery_event_data["email_message_id"] = email_message_id
        if email_in_reply_to:
            delivery_event_data["email_in_reply_to"] = email_in_reply_to
        if email_references:
            delivery_event_data["email_references"] = email_references

        # Send response event using shared utilities
        success = await event_sender.send_response_event(
            delivery_event_data,
            event_data.get("request_id"),  # type: ignore[arg-type]
            event_data.get("agent_id"),
            event_data.get("session_id"),
        )

        if success:
            logger.info(
                "Agent response forwarded to Integration Dispatcher",
                request_id=event_data.get("request_id"),
                session_id=event_data.get("session_id"),
                agent_id=event_data.get("agent_id"),
            )
        else:
            logger.error(
                "Failed to forward agent response to Integration Dispatcher",
                request_id=event_data.get("request_id"),
                session_id=event_data.get("session_id"),
                agent_id=event_data.get("agent_id"),
            )

        return success

    except Exception as e:
        logger.error(
            "Error forwarding response to Integration Dispatcher",
            error=str(e),
            request_id=event_data.get("request_id"),
            session_id=event_data.get("session_id"),
        )
        return False


@app.get("/api/v1/conversations")
async def get_conversations(
    session_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    integration_type: Optional[str] = None,
    integration_types: Optional[List[str]] = Query(
        None,
        description="Only include sessions that used at least one of these channels; full conversation returned. E.g. CLI,SLACK.",
    ),
    agent_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    random: bool = False,
    include_messages: bool = True,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Get conversations with flexible filtering. No auth required (matches generic).

    Query Parameters:
        session_id: Get specific session's conversation
        start_date: ISO 8601 datetime (e.g., 2026-01-01T00:00:00Z)
        end_date: ISO 8601 datetime
        user_id: UUID or email address to filter by user
        user_email: Email address to filter by user (alternative to user_id)
        integration_type: Filter by channel where the conversation started (session record)
        integration_types: Only include sessions that used at least one of these
            channels; returned conversations are full. E.g. ?integration_types=CLI&integration_types=SLACK
        agent_id: Only include sessions that used this agent at least once; returned
            conversations are full (routing + specialist + etc.). E.g. laptop-refresh.
        limit: Number of results (default: 100, max: 1000)
        offset: Pagination offset (default: 0)
        random: Random sampling instead of ordered (default: false)
        include_messages: Include full conversation messages (default: true)
    """
    from shared_models.models import IntegrationType, RequestLog, RequestSession
    from shared_models.user_utils import (
        get_or_create_canonical_user,
        is_uuid,
        resolve_canonical_user_id,
    )
    from sqlalchemy import exists, func, select
    from sqlalchemy.orm import selectinload

    # Validate limit
    if limit > 1000:
        limit = 1000
    if limit < 1:
        limit = 100

    # Build base query; eager-load user to avoid async lazy-load errors
    stmt = select(RequestSession).options(selectinload(RequestSession.user))

    # Filter by session_id if provided
    if session_id:
        stmt = stmt.where(RequestSession.session_id == session_id)

    # Resolve user filter (UUID or email)
    resolved_user_id = None
    if user_id or user_email:
        try:
            if user_id:
                if is_uuid(user_id):
                    resolved_user_id = user_id
                else:
                    # Treat as email
                    resolved_user_id = await resolve_canonical_user_id(user_id, db=db)
            elif user_email:
                resolved_user_id = await get_or_create_canonical_user(user_email, db)

            if resolved_user_id:
                stmt = stmt.where(RequestSession.user_id == resolved_user_id)
        except Exception as e:
            logger.warning(
                "Failed to resolve user_id filter",
                user_id=user_id,
                user_email=user_email,
                error=str(e),
            )
            # Continue without user filter if resolution fails

    # Filter by date range
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            stmt = stmt.where(RequestSession.created_at >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use ISO 8601 (e.g., 2026-01-01T00:00:00Z)",
            )

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            stmt = stmt.where(RequestSession.created_at <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use ISO 8601 (e.g., 2026-01-01T00:00:00Z)",
            )

    # Filter by integration_type
    if integration_type:
        try:
            integration_enum = IntegrationType(integration_type.upper())
            stmt = stmt.where(RequestSession.integration_type == integration_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration_type: {integration_type}. Valid values: {', '.join([e.value for e in IntegrationType])}",
            )

    # Filter by agent_id at query level so we get up to limit sessions that used this agent
    if agent_id:
        exists_stmt = select(1).where(
            RequestLog.session_id == RequestSession.session_id,
            RequestLog.agent_id == agent_id,
        )
        stmt = stmt.where(exists(exists_stmt))

    # Get total count before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    if random:
        stmt = stmt.order_by(func.random()).limit(limit).offset(offset)
    else:
        stmt = (
            stmt.order_by(RequestSession.last_request_at.desc())
            .limit(limit)
            .offset(offset)
        )

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    # Parse and validate integration_types filter (session used at least one of these channels)
    requested_integration_types: Optional[set[str]] = None
    if integration_types:
        requested_integration_types = set()
        for raw in integration_types:
            if not raw or not str(raw).strip():
                continue
            try:
                integration_enum = IntegrationType(str(raw).upper())
                requested_integration_types.add(integration_enum.value)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid integration_types value: {raw}. Valid values: {', '.join([e.value for e in IntegrationType])}",
                )
        if not requested_integration_types:
            requested_integration_types = None

    # Build response with optional conversation messages
    session_results = []
    for session in sessions:
        session_data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "integration_type": session.integration_type.value,
            "status": session.status.value,
            "created_at": session.created_at.isoformat(),
            "last_request_at": (
                session.last_request_at.isoformat() if session.last_request_at else None
            ),
            "total_requests": session.total_requests,
            "current_agent_id": session.current_agent_id,
            "current_thread_id": session.conversation_thread_id,
        }

        # Get user email if available
        if session.user:
            session_data["user_email"] = session.user.primary_email

        # Filter by agent_id if specified: include session only if it has at least one
        # message from that agent; return full conversation (routing + specialist + etc.)
        filter_by_agent = agent_id is not None

        # Include conversation messages if requested
        if include_messages:
            # Get all request logs for this session
            log_stmt = (
                select(RequestLog)
                .where(RequestLog.session_id == session.session_id)
                .order_by(RequestLog.created_at.asc())
            )
            log_result = await db.execute(log_stmt)
            request_logs = log_result.scalars().all()

            # Session-level filter: skip session if no message from the requested agent
            if filter_by_agent and not any(
                log.agent_id == agent_id for log in request_logs
            ):
                continue

            conversation = []
            integration_types_used: set[str] = set()
            for log in request_logs:
                # Extract thread_id from metadata or use session's current thread_id
                thread_id = None
                thread_id_source = "none"
                if log.response_metadata:
                    thread_id = log.response_metadata.get("conversation_thread_id")
                    if thread_id:
                        thread_id_source = "metadata"

                if not thread_id:
                    thread_id = session.conversation_thread_id
                    thread_id_source = "session"

                # Per-message origin: use integration_type from the request that created this log
                # (stored in normalized_request); fall back to session's type for older logs or if missing
                log_integration_type = None
                if log.normalized_request and isinstance(log.normalized_request, dict):
                    raw = log.normalized_request.get("integration_type")
                    log_integration_type = (
                        raw
                        if isinstance(raw, str)
                        else (getattr(raw, "value", None) if raw else None)
                    )
                if not log_integration_type:
                    log_integration_type = session.integration_type.value
                integration_types_used.add(log_integration_type)

                conversation.append(
                    {
                        "request_id": log.request_id,
                        "timestamp": log.created_at.isoformat(),
                        "integration_type": log_integration_type,
                        "user_message": log.request_content,
                        "agent_response": log.response_content,
                        "agent_id": log.agent_id,
                        "thread_id": thread_id,
                        "thread_id_source": thread_id_source,
                        "processing_time_ms": log.processing_time_ms,
                        "completed_at": (
                            log.completed_at.isoformat() if log.completed_at else None
                        ),
                    }
                )

            session_data["integration_types"] = sorted(integration_types_used)
            session_data["conversation"] = conversation

            # Session-level filter: skip if session used none of the requested channels
            if requested_integration_types and not (
                integration_types_used & requested_integration_types
            ):
                continue
        else:
            # No messages loaded: use session's single integration_type
            session_data["integration_types"] = [session.integration_type.value]
            # If filtering by agent_id but not including messages, check session's current_agent_id
            if filter_by_agent and session.current_agent_id != agent_id:
                continue
            # If filtering by integration_types, session's type must be in the set
            if (
                requested_integration_types
                and session.integration_type.value not in requested_integration_types
            ):
                continue

        session_results.append(session_data)

    logger.info(
        "Conversations retrieved",
        admin_user=(current_user or {}).get("user_id"),
        session_count=len(session_results),
        total=total,
        filters={
            "session_id": session_id,
            "start_date": start_date,
            "end_date": end_date,
            "user_id": resolved_user_id,
            "user_email": user_email,
            "integration_type": integration_type,
            "integration_types": (
                list(requested_integration_types)
                if requested_integration_types
                else None
            ),
            "agent_id": agent_id,
        },
    )

    return {
        "sessions": session_results,
        "count": len(session_results),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


if tracingIsActive():
    FastAPIInstrumentor.instrument_app(app)
