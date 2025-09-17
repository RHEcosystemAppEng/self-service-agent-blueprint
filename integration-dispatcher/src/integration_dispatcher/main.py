"""Main FastAPI application for Integration Dispatcher."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import structlog
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shared_db import get_enum_value
from shared_db.models import (
    DeliveryLog,
    DeliveryRequest,
    DeliveryStatus,
    ErrorResponse,
    IntegrationType,
    ProcessedEvent,
    UserIntegrationConfig,
)
from shared_db.session import get_database_manager, get_db_session
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .integrations.base import BaseIntegrationHandler
from .integrations.email import EmailIntegrationHandler
from .integrations.slack import SlackIntegrationHandler
from .integrations.test import TestIntegrationHandler
from .integrations.webhook import WebhookIntegrationHandler
from .schemas import (
    DeliveryLogResponse,
    HealthCheck,
    UserIntegrationConfigCreate,
    UserIntegrationConfigResponse,
    UserIntegrationConfigUpdate,
)
from .slack_schemas import (
    SlackChallenge,
    SlackInteractionPayload,
    SlackSlashCommand,
)
from .slack_service import SlackService
from .template_engine import TemplateEngine

# Configure structured logging
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


class IntegrationDispatcher:
    """Main dispatcher for managing integrations."""

    def __init__(self):
        self.handlers: Dict[IntegrationType, BaseIntegrationHandler] = {
            IntegrationType.SLACK: SlackIntegrationHandler(),
            IntegrationType.EMAIL: EmailIntegrationHandler(),
            IntegrationType.WEBHOOK: WebhookIntegrationHandler(),
            IntegrationType.TEST: TestIntegrationHandler(),
        }
        self.template_engine = TemplateEngine()

    async def dispatch(
        self,
        request: DeliveryRequest,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """Dispatch delivery request to all enabled integrations for user."""
        logger.info(
            "Starting integration dispatch",
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            agent_id=request.agent_id,
        )

        # Get user's integration configurations
        stmt = (
            select(UserIntegrationConfig)
            .where(
                UserIntegrationConfig.user_id == request.user_id,
                UserIntegrationConfig.enabled == True,  # noqa: E712
            )
            .order_by(UserIntegrationConfig.priority.desc())
        )

        result = await db.execute(stmt)
        configs = result.scalars().all()

        logger.info(
            "Retrieved user integration configs",
            user_id=request.user_id,
            request_id=request.request_id,
            configs_found=len(configs),
            integration_types=(
                [config.integration_type for config in configs] if configs else []
            ),
        )

        if not configs:
            logger.info(
                "No integrations configured for user",
                user_id=request.user_id,
                request_id=request.request_id,
                session_id=request.session_id,
            )
            return []

        # Dispatch to all configured integrations
        delivery_results = []

        for config in configs:
            try:
                result = await self._dispatch_single(request, config, db)
                delivery_results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to dispatch to integration",
                    user_id=request.user_id,
                    integration_type=config.integration_type,
                    error=str(e),
                )

                # Create failed delivery log
                await self._create_delivery_log(
                    request=request,
                    config=config,
                    status=DeliveryStatus.FAILED,
                    error_message=f"Dispatch error: {str(e)}",
                    db=db,
                )

        return delivery_results

    async def _dispatch_single(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Dispatch to a single integration."""
        handler = self.handlers.get(config.integration_type)
        if not handler:
            raise ValueError(
                f"No handler for integration type: {config.integration_type}"
            )

        # Render templates
        template_content = await self.template_engine.render(
            integration_type=config.integration_type,
            subject=request.subject,
            content=request.content,
            variables=request.template_variables,
            db=db,
        )

        # Create delivery log
        delivery_log = DeliveryLog(
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            integration_config_id=config.id,
            integration_type=get_enum_value(config.integration_type),
            subject=template_content.get("subject"),
            content=template_content.get("body"),
            template_used=template_content.get("template_name"),
            max_attempts=config.retry_count,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        db.add(delivery_log)
        await db.commit()
        await db.refresh(delivery_log)

        # Attempt delivery
        try:
            delivery_log.first_attempt_at = datetime.now(timezone.utc)
            delivery_log.last_attempt_at = datetime.now(timezone.utc)
            delivery_log.attempts = 1

            integration_result = await handler.deliver(
                request, config, template_content
            )

            # Update delivery log
            delivery_log.status = integration_result.status.value
            delivery_log.integration_metadata = integration_result.metadata

            if integration_result.success:
                delivery_log.delivered_at = datetime.now(timezone.utc)
                logger.info(
                    "Integration delivery successful",
                    user_id=request.user_id,
                    integration_type=config.integration_type,
                    request_id=request.request_id,
                )
            else:
                delivery_log.error_message = integration_result.message
                logger.warning(
                    "Integration delivery failed",
                    user_id=request.user_id,
                    integration_type=config.integration_type,
                    request_id=request.request_id,
                    error=integration_result.message,
                )

                # Schedule retry if applicable
                if (
                    integration_result.retry_after
                    and delivery_log.attempts < delivery_log.max_attempts
                ):
                    # In a real implementation, you'd schedule this with a task queue
                    logger.info(
                        "Scheduling retry",
                        retry_after=integration_result.retry_after,
                        attempt=delivery_log.attempts,
                        max_attempts=delivery_log.max_attempts,
                    )

            await db.commit()

            return {
                "delivery_id": delivery_log.id,
                "integration_type": get_enum_value(config.integration_type),
                "status": integration_result.status.value,
                "success": integration_result.success,
                "message": integration_result.message,
                "metadata": integration_result.metadata,
            }

        except Exception as e:
            delivery_log.status = DeliveryStatus.FAILED.value
            delivery_log.error_message = f"Handler error: {str(e)}"
            await db.commit()
            raise

    async def _create_delivery_log(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        status: DeliveryStatus,
        error_message: str,
        db: AsyncSession,
    ) -> None:
        """Create a delivery log entry for failed dispatch."""
        delivery_log = DeliveryLog(
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            integration_config_id=config.id,
            integration_type=get_enum_value(config.integration_type),
            subject=request.subject,
            content=request.content,
            status=status.value,
            error_message=error_message,
            attempts=1,
            max_attempts=config.retry_count,
            first_attempt_at=datetime.now(timezone.utc),
            last_attempt_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        db.add(delivery_log)
        await db.commit()


# Global dispatcher instance
dispatcher = IntegrationDispatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Integration Dispatcher", version=__version__)

    # Log environment variables (without sensitive data)
    logger.info(
        "Environment configuration",
        postgres_host=os.getenv("POSTGRES_HOST", "not_set"),
        postgres_port=os.getenv("POSTGRES_PORT", "not_set"),
        postgres_db=os.getenv("POSTGRES_DB", "not_set"),
        smtp_host=os.getenv("SMTP_HOST", "not_set"),
        smtp_port=os.getenv("SMTP_PORT", "not_set"),
        smtp_username=os.getenv("SMTP_USERNAME", "not_set"),
        slack_bot_token_configured=bool(os.getenv("SLACK_BOT_TOKEN")),
        broker_url=os.getenv("BROKER_URL", "not_set"),
    )

    # Initialize integration handlers
    logger.info(
        "Initializing integration handlers",
        total_handlers=len(dispatcher.handlers),
        handler_types=[get_enum_value(t) for t in dispatcher.handlers.keys()],
    )

    # Wait for database migration to complete
    logger.info("Waiting for database migration to complete...")
    db_manager = get_database_manager()
    try:
        migration_ready = await db_manager.wait_for_migration(timeout=300)
        if not migration_ready:
            raise Exception("Database migration did not complete within timeout")
        logger.info("Database migration verified and ready")
    except Exception as e:
        logger.error("Failed to verify database migration", error=str(e))
        raise

    # Test initial health check
    logger.info("Performing initial health check...")
    try:
        # This will help us see what's happening during startup
        from shared_db.session import get_db_session

        from .main import health_check

        async for db in get_db_session():
            health_result = await health_check(db)
            logger.info(
                "Initial health check completed",
                status=health_result.status,
                database_connected=health_result.database_connected,
                integrations_available=health_result.integrations_available,
            )
            break
    except Exception as e:
        logger.warning("Initial health check failed", error=str(e))

    logger.info("Integration Dispatcher startup completed successfully")

    yield

    # Shutdown
    logger.info("Shutting down Integration Dispatcher")
    await db_manager.close()


# Initialize Integration Dispatcher
dispatcher = IntegrationDispatcher()

# Create FastAPI application
app = FastAPI(
    title="Self-Service Agent Integration Dispatcher",
    description="Multi-tenant Integration Dispatcher for Self-Service Agent Blueprint",
    version=__version__,
    lifespan=lifespan,
)

# Initialize Slack service
slack_service = SlackService()


# Debug middleware to log all requests
@app.middleware("http")
async def debug_requests(request: Request, call_next):
    logger.info("Request received", method=request.method, path=request.url.path)
    response = await call_next(request)
    return response


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db_session)) -> HealthCheck:
    """Health check endpoint."""
    logger.info("Health check started")

    # Test database connection
    database_connected = False
    try:
        logger.info("Testing database connection...")
        await db.execute(text("SELECT 1"))
        database_connected = True
        logger.info("Database connection successful")
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        database_connected = False

    # Check integration handlers
    integrations_available = []
    integration_errors = {}

    logger.info(
        "Checking integration handlers", total_handlers=len(dispatcher.handlers)
    )

    for integration_type, handler in dispatcher.handlers.items():
        integration_name = get_enum_value(integration_type)
        try:
            logger.info("Testing integration health", integration=integration_name)
            if await handler.health_check():
                integrations_available.append(integration_name)
                logger.info(
                    "Integration health check passed", integration=integration_name
                )
            else:
                logger.warning(
                    "Integration health check failed", integration=integration_name
                )
        except Exception as e:
            logger.error(
                "Integration health check error",
                integration=integration_name,
                error=str(e),
            )
            integration_errors[integration_name] = str(e)

    logger.info(
        "Health check completed",
        database_connected=database_connected,
        integrations_available=integrations_available,
        integration_errors=integration_errors,
    )

    return HealthCheck(
        status="healthy" if database_connected else "degraded",
        database_connected=database_connected,
        integrations_available=integrations_available,
        services={
            "database": "connected" if database_connected else "disconnected",
            "integrations": f"{len(integrations_available)}/{len(dispatcher.handlers)} available",
        },
    )


@app.post("/notifications")
async def handle_notification_event(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Handle notification CloudEvents (request acknowledgments, status updates)."""
    try:
        headers = dict(request.headers)
        body = await request.body()

        logger.info(
            "Notification CloudEvent received",
            event_type=headers.get("ce-type"),
            source=headers.get("ce-source"),
            event_id=headers.get("ce-id"),
        )

        event_type = headers.get("ce-type")
        event_data = json.loads(body)

        # Handle different notification types
        if event_type == "com.self-service-agent.request.created":
            return await _handle_request_acknowledgment(event_data, db)
        elif event_type == "com.self-service-agent.request.processing":
            return await _handle_processing_notification(event_data, db)
        else:
            logger.info(
                "Notification event ignored",
                event_type=event_type,
                reason="unhandled notification type",
            )
            return {"status": "ignored", "reason": "unhandled notification type"}

    except Exception as e:
        logger.error(
            "Failed to handle notification CloudEvent",
            error=str(e),
            event_type=headers.get("ce-type") if "headers" in locals() else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process notification CloudEvent",
        )


@app.post("/")
async def handle_cloudevent(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Handle incoming CloudEvents for delivery requests."""

    event_id = None
    event_type = None
    event_source = None

    try:
        # Parse CloudEvent headers
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

        # Validate CloudEvent type
        if event_type != "com.self-service-agent.agent.response-ready":
            logger.info(
                "CloudEvent ignored",
                event_type=event_type,
                reason="unhandled event type",
            )
            # Still record the event as processed (ignored)
            await _record_processed_event(
                db,
                event_id,
                event_type,
                event_source,
                None,
                None,
                "integration-dispatcher",
                "ignored",
                "unhandled event type",
            )
            return {"status": "ignored", "reason": "unhandled event type"}

        # Parse event data
        event_data = json.loads(body)

        request_id = event_data.get("request_id")
        session_id = event_data.get("session_id")

        logger.info(
            "Parsing CloudEvent data",
            request_id=request_id,
            session_id=session_id,
            user_id=event_data.get("user_id"),
            agent_id=event_data.get("agent_id"),
        )

        # Create delivery request
        delivery_request = DeliveryRequest(
            request_id=event_data.get("request_id"),
            session_id=event_data.get("session_id"),
            user_id=event_data.get("user_id"),
            subject=event_data.get("subject"),
            content=event_data.get("content"),
            template_variables=event_data.get("template_variables", {}),
            agent_id=event_data.get("agent_id"),
        )

        logger.info(
            "DeliveryRequest created successfully",
            request_id=delivery_request.request_id,
            session_id=delivery_request.session_id,
            user_id=delivery_request.user_id,
            agent_id=delivery_request.agent_id,
            content_length=(
                len(delivery_request.content) if delivery_request.content else 0
            ),
        )

        # Dispatch to integrations
        results = await dispatcher.dispatch(delivery_request, db)

        logger.info(
            "CloudEvent processed successfully",
            request_id=delivery_request.request_id,
            session_id=delivery_request.session_id,
            user_id=delivery_request.user_id,
            agent_id=delivery_request.agent_id,
            integrations_dispatched=len(results),
            integration_results=[
                r.get("integration_type") for r in results if isinstance(r, dict)
            ],
        )

        # ✅ RECORD SUCCESSFUL EVENT PROCESSING
        await _record_processed_event(
            db,
            event_id,
            event_type,
            event_source,
            delivery_request.request_id,
            delivery_request.session_id,
            "integration-dispatcher",
            "success",
        )

        return {
            "status": "processed",
            "request_id": delivery_request.request_id,
            "dispatched_integrations": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(
            "Failed to handle CloudEvent",
            error=str(e),
            event_type=event_type,
            event_data_keys=list(event_data.keys()) if "event_data" in locals() else [],
        )

        # ✅ RECORD FAILED EVENT PROCESSING
        await _record_processed_event(
            db,
            event_id,
            event_type,
            event_source,
            event_data.get("request_id") if "event_data" in locals() else None,
            event_data.get("session_id") if "event_data" in locals() else None,
            "integration-dispatcher",
            "error",
            str(e),
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


@app.post("/deliver")
async def handle_direct_delivery(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Handle direct delivery requests (for non-eventing mode)."""
    try:
        print("=== DELIVER ENDPOINT CALLED ===")
        body = await request.body()
        delivery_data = json.loads(body)
        print(f"Delivery data: {delivery_data}")

        logger.info(
            "Direct delivery request received",
            request_id=delivery_data.get("request_id"),
            session_id=delivery_data.get("session_id"),
            user_id=delivery_data.get("user_id"),
        )

        # Create delivery request from the payload using shared model
        from shared_db.models import DeliveryRequest

        delivery_request = DeliveryRequest(
            request_id=delivery_data.get("request_id"),
            session_id=delivery_data.get("session_id"),
            user_id=delivery_data.get("user_id"),
            agent_id=delivery_data.get("agent_id"),
            subject=delivery_data.get("subject"),
            content=delivery_data.get("content"),
            template_variables=delivery_data.get("template_variables", {}),
        )

        # Dispatch to integrations
        logger.info(
            "About to dispatch delivery request",
            request_id=delivery_request.request_id,
            user_id=delivery_request.user_id,
            agent_id=delivery_request.agent_id,
        )

        results = await dispatcher.dispatch(delivery_request, db)
        print(f"Dispatch results: {results}")

        logger.info(
            "Dispatch completed",
            request_id=delivery_request.request_id,
            results_count=len(results) if results else 0,
            results=results,
        )

        return {
            "status": "success",
            "request_id": delivery_request.request_id,
            "deliveries": results,
        }

    except json.JSONDecodeError:
        logger.error("Invalid JSON in direct delivery request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error("Error handling direct delivery request", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


async def _handle_request_acknowledgment(
    event_data: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """Handle request acknowledgment notification."""
    request_id = event_data.get("request_id")
    user_id = event_data.get("user_id")
    session_id = event_data.get("session_id")

    logger.info(
        "Processing request acknowledgment",
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
    )

    # Create minimal acknowledgment message for user
    acknowledgment_request = DeliveryRequest(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        subject="Request Received",
        content="✅ Processing your request...",
        template_variables={"request_id": request_id, "status": "received"},
        agent_id=None,
    )

    # Send acknowledgment to user's configured integrations
    results = await dispatcher.dispatch(acknowledgment_request, db)

    logger.info(
        "Request acknowledgment sent",
        request_id=request_id,
        user_id=user_id,
        integrations_notified=len(results),
    )

    return {
        "status": "acknowledged",
        "request_id": request_id,
        "notifications_sent": len(results),
    }


async def _handle_processing_notification(
    event_data: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """Handle processing status notification (simplified - no user notification)."""
    request_id = event_data.get("request_id")
    user_id = event_data.get("user_id")
    session_id = event_data.get("session_id")
    agent_id = event_data.get("agent_id")

    logger.info(
        "Processing status notification (no user notification sent)",
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
        agent_id=agent_id,
    )

    # Skip sending processing notification to reduce Slack noise
    # Users will only see the final AI response

    return {
        "status": "processing_noted",
        "request_id": request_id,
        "agent_id": agent_id,
        "notifications_sent": 0,
    }


# User Integration Configuration API
@app.get(
    "/api/v1/users/{user_id}/integrations",
    response_model=List[UserIntegrationConfigResponse],
)
async def get_user_integrations(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> List[UserIntegrationConfigResponse]:
    """Get user's integration configurations."""
    stmt = (
        select(UserIntegrationConfig)
        .where(UserIntegrationConfig.user_id == user_id)
        .order_by(UserIntegrationConfig.priority.desc())
    )

    result = await db.execute(stmt)
    configs = result.scalars().all()

    return [UserIntegrationConfigResponse.from_orm(config) for config in configs]


@app.post(
    "/api/v1/users/{user_id}/integrations", response_model=UserIntegrationConfigResponse
)
async def create_user_integration(
    user_id: str,
    config_data: UserIntegrationConfigCreate,
    db: AsyncSession = Depends(get_db_session),
) -> UserIntegrationConfigResponse:
    """Create or update user integration configuration."""
    # Check if configuration already exists
    stmt = select(UserIntegrationConfig).where(
        UserIntegrationConfig.user_id == user_id,
        UserIntegrationConfig.integration_type
        == get_enum_value(config_data.integration_type),
    )

    result = await db.execute(stmt)
    existing_config = result.scalar_one_or_none()

    if existing_config:
        # Update existing configuration
        existing_config.enabled = config_data.enabled
        existing_config.config = config_data.config
        existing_config.priority = config_data.priority
        existing_config.retry_count = config_data.retry_count
        existing_config.retry_delay_seconds = config_data.retry_delay_seconds
        existing_config.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(existing_config)
        return UserIntegrationConfigResponse.from_orm(existing_config)
    else:
        # Create new configuration
        config = UserIntegrationConfig(
            user_id=user_id,
            integration_type=get_enum_value(config_data.integration_type),
            enabled=config_data.enabled,
            config=config_data.config,
            priority=config_data.priority,
            retry_count=config_data.retry_count,
            retry_delay_seconds=config_data.retry_delay_seconds,
        )

        db.add(config)
        await db.commit()
        await db.refresh(config)

        logger.info(
            "User integration configured",
            user_id=user_id,
            integration_type=get_enum_value(config_data.integration_type),
            enabled=config_data.enabled,
        )

        return UserIntegrationConfigResponse.from_orm(config)


@app.put(
    "/api/v1/users/{user_id}/integrations/{integration_type}",
    response_model=UserIntegrationConfigResponse,
)
async def update_user_integration(
    user_id: str,
    integration_type: IntegrationType,
    config_update: UserIntegrationConfigUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> UserIntegrationConfigResponse:
    """Update user integration configuration."""
    stmt = select(UserIntegrationConfig).where(
        UserIntegrationConfig.user_id == user_id,
        UserIntegrationConfig.integration_type == get_enum_value(integration_type),
    )

    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration configuration not found",
        )

    # Update fields
    update_data = config_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(config)

    return UserIntegrationConfigResponse.from_orm(config)


@app.delete("/api/v1/users/{user_id}/integrations/{integration_type}")
async def delete_user_integration(
    user_id: str,
    integration_type: IntegrationType,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, str]:
    """Delete user integration configuration."""
    stmt = select(UserIntegrationConfig).where(
        UserIntegrationConfig.user_id == user_id,
        UserIntegrationConfig.integration_type == get_enum_value(integration_type),
    )

    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration configuration not found",
        )

    await db.delete(config)
    await db.commit()

    logger.info(
        "User integration deleted",
        user_id=user_id,
        integration_type=get_enum_value(integration_type),
    )

    return {"message": "Integration configuration deleted"}


@app.get("/api/v1/users/{user_id}/deliveries", response_model=List[DeliveryLogResponse])
async def get_user_deliveries(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
) -> List[DeliveryLogResponse]:
    """Get user's delivery history."""
    stmt = (
        select(DeliveryLog)
        .where(DeliveryLog.user_id == user_id)
        .order_by(DeliveryLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    deliveries = result.scalars().all()

    return [DeliveryLogResponse.from_orm(delivery) for delivery in deliveries]


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


# Slack Integration Endpoints


@app.post("/slack/events")
async def handle_slack_events(request: Request):
    """Handle Slack events (messages, mentions, etc.)."""
    try:
        body = await request.body()
        headers = request.headers

        # Verify signature
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")

        if not slack_service.verify_slack_signature(body, timestamp, signature):
            logger.warning("Invalid Slack signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse the request
        data = json.loads(body.decode("utf-8"))

        # Handle URL verification challenge
        if data.get("type") == "url_verification":
            challenge = SlackChallenge(**data)
            return {"challenge": challenge.challenge}

        # Handle event
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_type = event.get("type")

            # Add debugging to see what events we're receiving
            logger.info(
                "Slack event received",
                event_type=event_type,
                event_subtype=event.get("subtype"),
                has_bot_id=bool(event.get("bot_id")),
                has_app_id=bool(event.get("app_id")),
                has_user=bool(event.get("user")),
                text_preview=event.get("text", "")[:50] if event.get("text") else None,
            )

            if event_type == "message":
                await slack_service.handle_message_event(event, data.get("team_id"))
            elif event_type == "app_mention":
                await slack_service.handle_message_event(event, data.get("team_id"))

            return {"status": "ok"}

        logger.warning("Unknown Slack event type", event_type=data.get("type"))
        return {"status": "ignored"}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Slack event")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error("Error handling Slack event", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/slack/interactive")
async def handle_slack_interactive(request: Request):
    """Handle Slack interactive components (buttons, etc.)."""
    try:
        body = await request.body()
        headers = request.headers

        # Verify signature
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")

        if not slack_service.verify_slack_signature(body, timestamp, signature):
            print("WARNING: Invalid Slack signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse form data
        form_data = body.decode("utf-8")
        if form_data.startswith("payload="):
            payload_json = form_data[8:]  # Remove "payload=" prefix
            import urllib.parse

            payload_json = urllib.parse.unquote(payload_json)
        else:
            payload_json = form_data

        data = json.loads(payload_json)
        payload = SlackInteractionPayload(**data)

        # Handle interaction
        if payload.type == "block_actions":
            response = await slack_service.handle_button_interaction(payload)
            return response
        elif payload.type == "view_submission":
            response = await slack_service.handle_modal_submission(payload)
            return response

        logger.warning("Unknown interaction type", interaction_type=payload.type)
        return {"text": "Unknown interaction"}

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in Slack interaction", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error("Error handling Slack interaction", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/slack/commands")
async def handle_slack_commands(
    token: str = Form(...),
    team_id: str = Form(...),
    team_domain: str = Form(...),
    channel_id: str = Form(...),
    channel_name: str = Form(...),
    user_id: str = Form(...),
    user_name: str = Form(...),
    command: str = Form(...),
    text: str = Form(...),
    response_url: str = Form(...),
    trigger_id: str = Form(...),
    api_app_id: str = Form(...),
):
    """Handle Slack slash commands."""
    try:
        # Create command object
        slash_command = SlackSlashCommand(
            token=token,
            team_id=team_id,
            team_domain=team_domain,
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            user_name=user_name,
            command=command,
            text=text,
            response_url=response_url,
            trigger_id=trigger_id,
            api_app_id=api_app_id,
        )

        # Handle the command
        response = await slack_service.handle_slash_command(slash_command)
        return response

    except Exception as e:
        logger.error("Error handling slash command", error=str(e))
        return {
            "response_type": "ephemeral",
            "text": "❌ Sorry, there was an error processing your command.",
        }


async def _record_processed_event(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    event_source: str,
    request_id: str,
    session_id: str,
    processed_by: str,
    processing_result: str,
    error_message: str = None,
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
        await db.rollback()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "integration_dispatcher.main:app",
        host=host,
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info",
    )
