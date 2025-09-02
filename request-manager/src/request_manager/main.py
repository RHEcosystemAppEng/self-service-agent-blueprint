"""Main FastAPI application for Request Manager."""

import json

# Configure structured logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from shared_models import (
    CloudEventSender,
    EventTypes,
    configure_logging,
    create_cloudevent_response,
    create_health_check_endpoint,
    create_shared_lifespan,
    generate_fallback_user_id,
    get_db_session_dependency,
    parse_cloudevent_from_request,
    verify_slack_signature,
)
from shared_models.models import (
    ErrorResponse,
    ProcessedEvent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    HealthCheck,
    SlackRequest,
    ToolRequest,
    WebRequest,
)

# Configure structured logging
logger = configure_logging("request-manager")


async def _request_manager_startup():
    """Custom startup logic for Request Manager."""
    # Initialize unified processor
    global unified_processor
    communication_strategy = get_communication_strategy()

    # Get agent client for session operations (only available in direct HTTP mode)
    from shared_clients import get_agent_client

    agent_client = get_agent_client()
    unified_processor = UnifiedRequestProcessor(communication_strategy, agent_client)
    logger.info(
        "Initialized unified request processor",
        strategy_type=type(communication_strategy).__name__,
        has_agent_client=agent_client is not None,
    )


# Create lifespan using shared utility with custom startup
def lifespan(app: FastAPI):
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
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
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


def verify_web_api_key(api_key: str) -> Optional[str]:
    """Verify web API key and return associated user email."""
    if not API_KEYS_ENABLED or not api_key:
        return None

    return WEB_API_KEYS.get(api_key)


async def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
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


@app.get("/health", response_model=HealthCheck)
async def health_check(
    db: AsyncSession = Depends(get_db_session_dependency),
) -> HealthCheck:
    """Health check endpoint."""
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


@app.get("/api/v1/requests/{request_id}")
async def get_request_status(
    request_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get request status and response by request ID.

    Note: Request logging is now handled by the Agent Service.
    This endpoint is deprecated and should be redirected to the Agent Service.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Request status endpoint moved to Agent Service - use Agent Service API instead",
    )


@app.post("/api/v1/requests/slack")
async def handle_slack_request(
    slack_request: SlackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
    x_slack_signature: Optional[str] = Header(None, alias="x-slack-signature"),
    x_slack_request_timestamp: Optional[str] = Header(
        None, alias="x-slack-request-timestamp"
    ),
) -> Dict[str, Any]:
    """Handle Slack integration requests with signature verification."""
    # Verify Slack signature if configured
    if SLACK_SIGNING_SECRET and x_slack_signature and x_slack_request_timestamp:
        body = await request.body()
        if not verify_slack_signature(
            body, x_slack_request_timestamp, x_slack_signature, SLACK_SIGNING_SECRET
        ):
            logger.warning("Invalid Slack signature", user_id=slack_request.user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
            )

    # Slack requires async processing due to 3-second timeout limit
    # Use async processing with background delivery for direct HTTP mode
    return await _process_request_async_with_delivery(slack_request, db)


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


@app.post("/api/v1/requests/generic/sync")
async def handle_generic_request_sync(
    request: BaseRequest,
    db: AsyncSession = Depends(get_db_session_dependency),
    timeout: int = 120,
) -> Dict[str, Any]:
    """Handle generic requests synchronously - waits for AI response."""
    return await _process_request_sync(request, db, timeout)


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

        # ✅ CIRCUIT BREAKER: Prevent feedback loops by ignoring self-generated events
        if event_source and (
            "request-manager" in event_source or event_source == "request-manager"
        ):
            logger.info(
                "Ignoring self-generated event to prevent feedback loop",
                event_id=event_id,
                event_type=event_type,
                event_source=event_source,
            )
            return {"status": "ignored", "reason": "self-generated event"}

        # ✅ EVENT ID DEDUPLICATION: Check if this exact event was already processed
        if event_id:
            existing_event = await db.execute(
                select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
            )
            if existing_event.scalar_one_or_none():
                logger.info(
                    "Event already processed - skipping duplicate",
                    event_id=event_id,
                    event_type=event_type,
                    event_source=event_source,
                )
                return {
                    "status": "skipped",
                    "reason": "duplicate event",
                    "event_id": event_id,
                }

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
    request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
    db: AsyncSession,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Process a request using the appropriate method based on eventing configuration."""
    if not unified_processor:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified processor not initialized",
        )

    try:
        # In direct HTTP mode, process synchronously
        # In eventing mode, process asynchronously
        eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"

        if eventing_enabled:
            return await unified_processor.process_request_async(request, db)
        else:
            return await unified_processor.process_request_sync(request, db, timeout)
    except Exception as e:
        logger.error("Failed to process request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        )


async def _process_request(
    request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
    db: AsyncSession,
) -> Dict[str, Any]:
    """Process an incoming request using unified processor."""
    if not unified_processor:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified processor not initialized",
        )

    try:
        return await unified_processor.process_request_async(request, db)
    except Exception as e:
        logger.error("Failed to process request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        )


async def _process_request_sync(
    request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
    db: AsyncSession,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Process a request synchronously and wait for AI response using unified processor."""
    if not unified_processor:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified processor not initialized",
        )

    try:
        return await unified_processor.process_request_sync(request, db, timeout)
    except Exception as e:
        logger.error("Failed to process synchronous request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        )


async def _process_request_async_with_delivery(
    request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
    db: AsyncSession,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Process a request asynchronously with background delivery for direct HTTP mode."""
    if not unified_processor:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unified processor not initialized",
        )

    try:
        return await unified_processor.process_request_async_with_delivery(
            request, db, timeout
        )
    except Exception as e:
        logger.error(
            "Failed to process request asynchronously with delivery", error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        )


async def _handle_agent_response_event_from_data(
    event_data: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """Handle agent response CloudEvent using unified response handler with pre-parsed data."""

    event_id = event_data.get("id")
    event_type = event_data.get("type")
    event_source = event_data.get("source")

    try:
        # Extract the actual event data from the CloudEvent data field
        response_data = event_data.get("data", {})

        # Extract response information
        request_id = response_data.get("request_id")
        session_id = response_data.get("session_id")
        agent_id = response_data.get("agent_id")
        content = response_data.get("content")
        user_id = response_data.get("user_id")

        if not all([request_id, session_id, content]):
            raise ValueError("Missing required fields in agent response")

        # Handle missing user_id gracefully
        if not user_id:
            logger.warning(
                "Missing user_id in agent response event, using fallback",
                request_id=request_id,
                session_id=session_id,
            )
            user_id = generate_fallback_user_id(request_id)

        # Use unified response handler
        response_handler = UnifiedResponseHandler(db)
        result = await response_handler.process_agent_response(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            content=content,
            metadata=event_data.get("metadata", {}),
            processing_time_ms=event_data.get("processing_time_ms"),
            requires_followup=event_data.get("requires_followup", False),
            followup_actions=event_data.get("followup_actions", []),
        )

        # Only forward response to Integration Dispatcher if it was actually processed
        if result.get("status") == "processed":
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
        await _record_processed_event(
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
        await _record_processed_event(
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
        content=ErrorResponse(
            error=exc.detail,
            error_code=f"HTTP_{exc.status_code}",
            timestamp=datetime.now(timezone.utc),
        ).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error("Unhandled exception", error=str(exc), path=str(request.url))

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            error_code="INTERNAL_ERROR",
            timestamp=datetime.now(timezone.utc),
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
            "template_variables": event_data.get(
                "template_variables", {}
            ),  # Default to empty dict if not present
            "agent_id": event_data.get("agent_id"),
        }

        # Send response event using shared utilities
        success = await event_sender.send_response_event(
            delivery_event_data,
            event_data.get("request_id"),
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


async def _record_processed_event(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    event_source: str,
    request_id: Optional[str],
    session_id: Optional[str],
    processed_by: str,
    processing_result: str,
    error_message: Optional[str] = None,
) -> None:
    """Record that an event has been processed to prevent duplicate processing."""
    if not event_id:
        logger.warning("Cannot record processed event without event_id")
        return

    try:
        processed_event = ProcessedEvent(
            event_id=event_id,
            event_type=event_type,
            event_source=event_source,
            request_id=request_id,
            session_id=session_id,
            processed_by=processed_by,
            processing_result=processing_result,
            error_message=error_message,
        )

        db.add(processed_event)
        await db.commit()

        logger.debug(
            "Recorded processed event",
            event_id=event_id,
            event_type=event_type,
            processing_result=processing_result,
        )

    except Exception as e:
        # Handle unique constraint violations gracefully (event already recorded)
        if "duplicate key value violates unique constraint" in str(e):
            logger.debug(
                "Event already recorded in processed_events table",
                event_id=event_id,
                processing_result=processing_result,
            )
        else:
            logger.error(
                "Failed to record processed event",
                event_id=event_id,
                error=str(e),
            )
