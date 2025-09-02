"""Main FastAPI application for Request Manager."""

import hashlib
import hmac
import json

# Configure structured logging
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import httpx
import jwt
import structlog
from cloudevents.http import CloudEvent
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from shared_db import get_enum_value
from shared_db.models import ProcessedEvent, RequestLog, RequestSession
from shared_db.session import get_database_manager, get_db_session
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .events import EventTypes, get_event_publisher
from .normalizer import RequestNormalizer
from .schemas import (
    BaseRequest,
    CLIRequest,
    ErrorResponse,
    HealthCheck,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
    SlackRequest,
    ToolRequest,
    WebRequest,
)
from .session_manager import SessionManager

# Set up basic logging to stdout
logging.basicConfig(
    level=logging.DEBUG if os.getenv("LOG_LEVEL", "INFO") == "DEBUG" else logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Request Manager", version=__version__)

    # Wait for database migration to complete
    db_manager = get_database_manager()
    try:
        migration_ready = await db_manager.wait_for_migration(timeout=300)
        if not migration_ready:
            raise Exception("Database migration did not complete within timeout")
        logger.info("Database migration verified and ready")
    except Exception as e:
        logger.error("Failed to verify database migration", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down Request Manager")

    # Close database connections
    await db_manager.close()

    # Close event publisher
    event_publisher = get_event_publisher()
    await event_publisher.close()


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

# Service Mesh configuration
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


def verify_slack_signature(
    body: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    """Verify Slack request signature."""
    if not secret:
        logger.warning("Slack signing secret not configured")
        return True  # Skip verification if not configured

    # Check timestamp to prevent replay attacks
    current_time = int(time.time())
    request_time = int(timestamp)

    if abs(current_time - request_time) > 300:  # 5 minutes
        return False

    # Verify signature
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_signature = (
        "v0="
        + hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    )

    return hmac.compare_digest(expected_signature, signature)


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

    # Legacy: Check for Istio-injected user headers (from JWT)
    # This is kept for backward compatibility with service mesh deployments
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
        user_info["auth_method"] = "service_mesh"
        logger.info("User authenticated via service mesh headers", user_id=user_id)
        return user_info

    logger.warning("No valid authentication method found")
    return None


@app.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db_session)) -> HealthCheck:
    """Health check endpoint."""
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        database_connected = True
    except Exception:
        database_connected = False

    return HealthCheck(
        status="healthy" if database_connected else "degraded",
        database_connected=database_connected,
        services={
            "database": "connected" if database_connected else "disconnected",
            "event_publisher": "ready",
        },
    )


@app.post("/api/v1/sessions", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Create a new session."""
    session_manager = SessionManager(db)

    try:
        session = await session_manager.create_session(session_data)

        # Publish session created event
        event_publisher = get_event_publisher()
        await event_publisher.publish_session_event(
            session.session_id,
            EventTypes.SESSION_CREATED,
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "integration_type": get_enum_value(session.integration_type),
                "created_at": session.created_at.isoformat(),
            },
        )

        logger.info(
            "Session created",
            session_id=session.session_id,
            user_id=session.user_id,
            integration_type=get_enum_value(session.integration_type),
        )

        return session

    except Exception as e:
        logger.error("Failed to create session", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


@app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Get session information."""
    session_manager = SessionManager(db)

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
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """Update session information."""
    session_manager = SessionManager(db)

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
        llama_stack_session_id=session_update.llama_stack_session_id,
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


@app.get("/api/v1/requests/{request_id}")
async def get_request_status(
    request_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get request status and response by request ID."""
    # Find the request log
    stmt = select(RequestLog).where(RequestLog.request_id == request_id)
    result = await db.execute(stmt)
    request_log = result.scalar_one_or_none()

    if not request_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    # Check if user has access to this request (via session)
    session_stmt = select(RequestSession).where(
        RequestSession.session_id == request_log.session_id
    )
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Verify user access (if authentication is enabled)
    if current_user and current_user.get("user_id") != session.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Return request status
    response_data = {
        "request_id": request_log.request_id,
        "session_id": request_log.session_id,
        "status": "completed" if request_log.response_content else "processing",
        "created_at": (
            request_log.created_at.isoformat() if request_log.created_at else None
        ),
        "completed_at": (
            request_log.completed_at.isoformat() if request_log.completed_at else None
        ),
    }

    # Include response content if available
    if request_log.response_content:
        response_data["response"] = {
            "content": request_log.response_content,
            "agent_id": request_log.agent_id,
            "metadata": request_log.response_metadata or {},
            "processing_time_ms": request_log.processing_time_ms,
        }

    return response_data


@app.post("/api/v1/requests/slack")
async def handle_slack_request(
    slack_request: SlackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
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

    return await _process_request(slack_request, db)


@app.post("/api/v1/requests/web")
async def handle_web_request(
    web_request: WebRequest,
    db: AsyncSession = Depends(get_db_session),
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

    return await _process_request(web_request, db)


@app.post("/api/v1/requests/cli")
async def handle_cli_request(
    cli_request: CLIRequest,
    db: AsyncSession = Depends(get_db_session),
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

    return await _process_request(cli_request, db)


@app.post("/api/v1/requests/tool")
async def handle_tool_request(
    tool_request: ToolRequest,
    db: AsyncSession = Depends(get_db_session),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
) -> Dict[str, Any]:
    """Handle tool-generated requests with API key authentication."""
    # Verify API key for tool requests
    if not verify_api_key(x_api_key or "", tool_request.tool_id):
        logger.warning("Invalid API key for tool request", tool_id=tool_request.tool_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    return await _process_request(tool_request, db)


@app.post("/api/v1/requests/generic")
async def handle_generic_request(
    request: BaseRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Handle generic requests."""
    return await _process_request(request, db)


@app.post("/api/v1/requests/generic/sync")
async def handle_generic_request_sync(
    request: BaseRequest,
    db: AsyncSession = Depends(get_db_session),
    timeout: int = 120,
) -> Dict[str, Any]:
    """Handle generic requests synchronously - waits for AI response."""
    return await _process_request_sync(request, db, timeout)


@app.post("/api/v1/events/cloudevents")
async def handle_cloudevent(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Handle incoming CloudEvents (e.g., from agent responses)."""
    try:
        # Parse CloudEvent from request
        headers = dict(request.headers)
        body = await request.body()

        event_id = headers.get("ce-id")
        event_type = headers.get("ce-type")
        event_source = headers.get("ce-source")

        logger.info(
            "CloudEvent received",
            event_id=event_id,
            event_type=event_type,
            event_source=event_source,
        )

        # ✅ CIRCUIT BREAKER: Prevent feedback loops by ignoring self-generated events
        if event_source == "request-manager":
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
            return await _handle_agent_response_event(headers, body, db)

        logger.warning("Unhandled CloudEvent type", event_type=event_type)
        return {"status": "ignored", "reason": "unhandled event type"}

    except Exception as e:
        logger.error("Failed to handle CloudEvent", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


async def _process_request(
    request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
    db: AsyncSession,
) -> Dict[str, Any]:
    """Process an incoming request."""
    session_manager = SessionManager(db)
    event_publisher = get_event_publisher()

    try:
        # Find or create session
        session = await session_manager.find_or_create_session(
            user_id=request.user_id,
            integration_type=request.integration_type,
            channel_id=getattr(request, "channel_id", None),
            thread_id=getattr(request, "thread_id", None),
            integration_metadata=request.metadata,
        )

        # Normalize the request
        normalized_request = normalizer.normalize_request(
            request, session.session_id, session.current_agent_id
        )

        # Log the request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            request_type=request.request_type,
            request_content=request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        await session_manager.increment_request_count(
            session.session_id, normalized_request.request_id
        )

        # Publish request event to broker
        success = await event_publisher.publish_request_event(
            normalized_request, EventTypes.REQUEST_CREATED
        )

        if not success:
            logger.error("Failed to publish request event")
            # Continue processing even if event publishing fails

        logger.info(
            "Request processed",
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            user_id=request.user_id,
            integration_type=get_enum_value(request.integration_type),
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session.session_id,
            "status": "accepted",
            "message": "Request has been queued for processing",
        }

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
    """Process a request synchronously and wait for AI response."""
    import asyncio

    session_manager = SessionManager(db)
    event_publisher = get_event_publisher()

    try:
        # Find or create session
        session = await session_manager.find_or_create_session(
            user_id=request.user_id,
            integration_type=request.integration_type,
            channel_id=getattr(request, "channel_id", None),
            thread_id=getattr(request, "thread_id", None),
            integration_metadata=request.metadata,
        )

        # Normalize the request
        normalized_request = normalizer.normalize_request(
            request, session.session_id, session.current_agent_id
        )

        # Log the request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            request_type=request.request_type,
            request_content=request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        await session_manager.increment_request_count(
            session.session_id, normalized_request.request_id
        )

        # Publish request event to broker
        success = await event_publisher.publish_request_event(
            normalized_request, EventTypes.REQUEST_CREATED
        )

        if not success:
            logger.error("Failed to publish request event")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to publish request event",
            )

        logger.info(
            "Request processed, waiting for response",
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            user_id=request.user_id,
            timeout=timeout,
        )

        # Wait for AI response with timeout
        response_data = await _wait_for_response(
            normalized_request.request_id, timeout, db
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session.session_id,
            "status": "completed",
            "response": response_data,
        }

    except asyncio.TimeoutError:
        logger.warning(
            "Request timeout waiting for response",
            request_id=(
                normalized_request.request_id
                if "normalized_request" in locals()
                else "unknown"
            ),
            timeout=timeout,
        )
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Request timed out after {timeout} seconds",
        )
    except Exception as e:
        logger.error("Failed to process synchronous request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request",
        )


async def _wait_for_response(
    request_id: str, timeout: int, db: AsyncSession
) -> Dict[str, Any]:
    """Wait for agent response by polling the database."""
    import asyncio
    from datetime import datetime, timedelta

    from shared_db.models import RequestLog
    from sqlalchemy import select

    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=timeout)

    while datetime.now() < end_time:
        # Use a fresh query with explicit session refresh to see committed changes
        await db.rollback()  # Clear any pending transaction

        # Check if response has been received
        stmt = select(RequestLog).where(RequestLog.request_id == request_id)
        result = await db.execute(stmt)
        request_log = result.scalar_one_or_none()

        if request_log:
            logger.debug(
                "Polling database for response",
                request_id=request_id,
                has_response_content=bool(request_log.response_content),
                response_content_length=(
                    len(request_log.response_content)
                    if request_log.response_content
                    else 0
                ),
                completed_at=request_log.completed_at,
            )

            if request_log.response_content:
                logger.info(
                    "Response received for synchronous request",
                    request_id=request_id,
                    elapsed_seconds=(datetime.now() - start_time).total_seconds(),
                )
                return {
                    "agent_id": request_log.agent_id,
                    "content": request_log.response_content,
                    "metadata": request_log.response_metadata or {},
                    "processing_time_ms": request_log.processing_time_ms,
                    "completed_at": (
                        request_log.completed_at.isoformat()
                        if request_log.completed_at
                        else None
                    ),
                }
        else:
            logger.debug(
                "Request log not found yet",
                request_id=request_id,
                elapsed_seconds=(datetime.now() - start_time).total_seconds(),
            )

        # Wait before polling again
        await asyncio.sleep(1)

    # Timeout reached
    raise asyncio.TimeoutError(f"No response received within {timeout} seconds")


async def _handle_agent_response_event(
    headers: Dict[str, str], body: bytes, db: AsyncSession
) -> Dict[str, Any]:
    """Handle agent response CloudEvent."""

    event_id = headers.get("ce-id")
    event_type = headers.get("ce-type")
    event_source = headers.get("ce-source")

    try:
        event_data = json.loads(body)

        # Extract response information
        request_id = event_data.get("request_id")
        session_id = event_data.get("session_id")
        agent_id = event_data.get("agent_id")
        content = event_data.get("content")

        if not all([request_id, session_id, content]):
            raise ValueError("Missing required fields in agent response")

        # ✅ BUSINESS LOGIC DEDUPLICATION: Check if this request already has a response
        # This is separate from event deduplication and handles business logic
        stmt = select(RequestLog).where(
            RequestLog.request_id == request_id,
            RequestLog.response_content.is_not(None),  # Already has a response
        )
        result = await db.execute(stmt)
        existing_response = result.scalar_one_or_none()

        if existing_response:
            logger.info(
                "Request already has response - skipping business logic",
                request_id=request_id,
                session_id=session_id,
                agent_id=agent_id,
            )
            # Still record the event as processed
            await _record_processed_event(
                db,
                event_id,
                event_type,
                event_source,
                request_id,
                session_id,
                "request-manager",
                "skipped",
                "request already has response",
            )
            return {
                "status": "skipped",
                "reason": "response already processed",
                "request_id": request_id,
            }

        # Check if this is a routing response that should switch agents
        session_manager = SessionManager(db)
        routed_agent = await _detect_and_validate_agent_routing(content, agent_id)

        if routed_agent:
            # Update session to use the routed agent and clear LlamaStack session
            # Agent-service will create a new LlamaStack session automatically via _get_or_create_session
            await session_manager.update_session(
                session_id,
                agent_id=routed_agent,
                llama_stack_session_id=None,  # Clear to let agent-service create new session
            )
            logger.info(
                "Agent routing detected and validated - session updated with new agent",
                session_id=session_id,
                from_agent=agent_id,
                to_agent=routed_agent,
                routing_response=content.strip(),
                llama_stack_session_cleared=True,
            )

            # Re-send the original user request to the newly routed agent
            await _resend_original_request_to_routed_agent(
                db, request_id, session_id, routed_agent
            )

        # Update request log with response
        stmt = (
            update(RequestLog)
            .where(RequestLog.request_id == request_id)
            .values(
                response_content=content,
                response_metadata=event_data.get("metadata", {}),
                agent_id=agent_id,
                processing_time_ms=event_data.get("processing_time_ms"),
                completed_at=datetime.now(timezone.utc),
                cloudevent_id=headers.get("ce-id"),
                cloudevent_type=headers.get("ce-type"),
            )
        )

        await db.execute(stmt)
        await db.commit()

        # Forward response to Integration Dispatcher for delivery to user
        await _forward_response_to_integration_dispatcher(
            event_data, routed_agent is not None
        )

        logger.info(
            "Agent response received and forwarded",
            request_id=request_id,
            session_id=session_id,
            agent_id=agent_id,
            routed_to_agent=routed_agent,
        )

        # ✅ RECORD SUCCESSFUL EVENT PROCESSING
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

        # ✅ RECORD FAILED EVENT PROCESSING
        await _record_processed_event(
            db,
            event_id,
            event_type,
            event_source,
            event_data.get("request_id") if "event_data" in locals() else None,
            event_data.get("session_id") if "event_data" in locals() else None,
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


async def _detect_and_validate_agent_routing(
    content: str,
    current_agent_id: str,
    available_agents: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Detect routing signals in agent responses.

    Supports two routing signals:
    1. task_complete_return_to_router - routes back to routing agent (from any agent)
    2. ROUTE_TO: [agent-name] - routes to specific agent (from routing agent)
    """

    # Get available agents if not provided
    if available_agents is None:
        available_agents = await _get_available_agents()

    agent_response = content.strip()

    # Check for task completion signal first (from any agent)
    if "task_complete_return_to_router" in agent_response:
        logger.info(
            "Task completion signal detected - routing back to router",
            current_agent_id=current_agent_id,
            response=agent_response,
        )
        return "routing-agent"

    # Check for structured routing response (ROUTE_TO: agent-name)
    # Look for ROUTE_TO: anywhere in the response, not just at the start
    if "ROUTE_TO:" in agent_response:
        # Extract the target agent from the ROUTE_TO: line
        lines = agent_response.split("\n")
        for line in lines:
            if line.strip().startswith("ROUTE_TO:"):
                target_agent = line.split(":", 1)[1].strip()
                if target_agent in available_agents:
                    logger.info(
                        "Structured routing detected",
                        routing_response=agent_response,
                        target_agent_name=target_agent,
                        target_agent_uuid=available_agents[target_agent],
                        current_agent_id=current_agent_id,
                    )
                    return target_agent
                else:
                    logger.warning(
                        "Invalid target agent in structured routing",
                        routing_response=agent_response,
                        target_agent=target_agent,
                        available_agents=list(available_agents.keys()),
                    )
                break

    logger.warning(
        "No valid routing signal detected - ignoring",
        routing_response=agent_response,
        available_agents=list(available_agents.keys()),
        current_agent_id=current_agent_id,
    )

    return None


async def _get_available_agents() -> Dict[str, str]:
    """Get list of available agents from agent-service."""
    try:
        # Get agent-service host from environment
        agent_service_host = os.getenv("AGENT_SERVICE_HOST", "agent-service")
        agent_service_port = os.getenv("AGENT_SERVICE_PORT", "8080")
        base_url = f"http://{agent_service_host}:{agent_service_port}"

        # Call agent-service API to get agents
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{base_url}/agents")
            response.raise_for_status()

            data = response.json()
            agents = data.get("agents", {})

            logger.info(
                "Retrieved available agents from agent-service",
                count=len(agents),
                agents=list(agents.keys()),
            )
            return agents

    except Exception as e:
        logger.error("Failed to get available agents from agent-service", error=str(e))
        # Return empty dict - validation will fail gracefully
        return {}


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

        # Publish response event for Integration Dispatcher to deliver
        event_publisher = get_event_publisher()

        # Create delivery event data for Integration Dispatcher
        # This matches the structure expected by DeliveryRequest in Integration Dispatcher
        delivery_event_data = {
            "request_id": event_data.get("request_id"),
            "session_id": event_data.get("session_id"),
            "user_id": event_data.get("user_id"),  # This was missing!
            "subject": event_data.get("subject"),
            "content": event_data.get("content"),
            "template_variables": event_data.get("template_variables", {}),
            "agent_id": event_data.get("agent_id"),
        }

        # Create CloudEvent for Integration Dispatcher
        event = CloudEvent(
            {
                "specversion": "1.0",
                "type": "com.self-service-agent.agent.response-ready",
                "source": "request-manager",
                "id": str(uuid.uuid4()),
                "time": datetime.now(timezone.utc).isoformat(),
                "subject": f"session/{event_data.get('session_id')}",
                "datacontenttype": "application/json",
            },
            delivery_event_data,
        )

        # Publish directly to broker
        success = await event_publisher._publish_event(event)

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


def _create_introduction_request(original_request, session):
    """Create a simple request with introduction message."""

    # Create a minimal request object with just the essentials
    class IntroductionRequest:
        def __init__(self):
            self.content = "please introduce yourself and tell me how you can help"
            self.user_id = session.user_id
            self.integration_type = session.integration_type
            self.request_type = "ROUTED_REQUEST"
            self.timestamp = datetime.now(timezone.utc)
            self.metadata = getattr(original_request, "metadata", {})

            # Add Slack-specific attributes if needed
            if hasattr(session, "channel_id"):
                self.channel_id = session.channel_id
            if hasattr(session, "thread_id"):
                self.thread_id = session.thread_id
            if hasattr(original_request, "slack_user_id"):
                self.slack_user_id = original_request.slack_user_id
            if hasattr(original_request, "slack_team_id"):
                self.slack_team_id = original_request.slack_team_id

    return IntroductionRequest()


async def _resend_original_request_to_routed_agent(
    db: AsyncSession, original_request_id: str, session_id: str, routed_agent: str
) -> None:
    """Re-send the original user request to the newly routed agent."""
    try:
        # Get the original request details and session info
        stmt = select(RequestLog).where(RequestLog.request_id == original_request_id)
        result = await db.execute(stmt)
        original_request = result.scalar_one_or_none()

        if not original_request:
            logger.error(
                "Could not find original request to re-send",
                original_request_id=original_request_id,
            )
            return

        # Get session info to get user_id
        session_stmt = select(RequestSession).where(
            RequestSession.session_id == session_id
        )
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()

        if not session:
            logger.error(
                "Could not find session for re-sending request",
                session_id=session_id,
            )
            return

        # Create a new request with the same content but targeting the routed agent
        normalizer = RequestNormalizer()

        # Create a dummy request object with the original content
        class RoutedRequest:
            def __init__(self, content: str, user_id: str):
                self.content = content
                self.user_id = user_id
                self.timestamp = datetime.now(timezone.utc)

        dummy_request = RoutedRequest(
            content=original_request.request_content, user_id=session.user_id
        )

        # Use introduction message for routed agents (like chat.py does)
        # Pass session info to ensure we have the correct integration_type
        routed_request = _create_introduction_request(dummy_request, session)

        # Normalize the request targeting the routed agent
        normalized_request = normalizer.normalize_request(
            routed_request, session_id, routed_agent
        )

        logger.info(
            "Sending introduction request to routed agent",
            original_request_id=original_request_id,
            new_request_id=normalized_request.request_id,
            session_id=session_id,
            routed_agent=routed_agent,
            original_content=original_request.request_content,
            introduction_content=routed_request.content,
        )

        # Log the re-sent request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session_id,
            request_type="ROUTED_REQUEST",
            request_content=routed_request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        # Publish request event to broker (same as normal request processing)
        event_publisher = get_event_publisher()
        success = await event_publisher.publish_request_event(
            normalized_request, EventTypes.REQUEST_CREATED
        )

        if not success:
            logger.error(
                "Failed to publish routed request event",
                request_id=normalized_request.request_id,
            )

    except Exception as e:
        logger.error(
            "Failed to re-send original request to routed agent",
            original_request_id=original_request_id,
            session_id=session_id,
            routed_agent=routed_agent,
            error=str(e),
        )
