"""Main FastAPI application for Integration Dispatcher."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shared_models import (
    EventTypes,
    HealthChecker,
    configure_logging,
    create_cloudevent_response,
    create_health_check_endpoint,
    create_shared_lifespan,
    get_database_manager,
    get_db_session_dependency,
    get_enum_value,
    parse_cloudevent_from_request,
)
from shared_models.models import (
    DeliveryLog,
    DeliveryRequest,
    DeliveryStatus,
    ErrorResponse,
    IntegrationType,
    ProcessedEvent,
    UserIntegrationConfig,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .integrations.base import BaseIntegrationHandler
from .integrations.defaults import IntegrationDefaultsService
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
from .slack_schemas import SlackChallenge, SlackInteractionPayload, SlackSlashCommand
from .slack_service import SlackService
from .template_engine import TemplateEngine

# Configure structured logging
logger = configure_logging("integration-dispatcher")


class IntegrationDispatcher:
    """Main dispatcher for managing integrations."""

    def __init__(self) -> None:
        self.handlers: Dict[IntegrationType, BaseIntegrationHandler] = {
            IntegrationType.SLACK: SlackIntegrationHandler(),
            IntegrationType.EMAIL: EmailIntegrationHandler(),
            IntegrationType.WEBHOOK: WebhookIntegrationHandler(),
            IntegrationType.TEST: TestIntegrationHandler(),
        }
        self.template_engine = TemplateEngine()

    def _ensure_slack_config_has_identifiers(
        self, user_config: Any, user_id: str
    ) -> None:
        """Ensure Slack config has necessary identifiers for channel resolution."""
        has_channel = bool(user_config.config.get("channel_id"))
        has_user_email = bool(user_config.config.get("user_email"))
        has_slack_user_id = bool(user_config.config.get("slack_user_id"))

        if not (has_channel or has_user_email or has_slack_user_id):
            # Add slack_user_id as fallback
            user_config.config["slack_user_id"] = user_id
            logger.info(
                "Added slack_user_id to existing Slack config",
                user_id=user_id,
                config=user_config.config,
            )

    async def _get_user_integration_configs(
        self, user_id: str, db: AsyncSession, request: Optional[DeliveryRequest] = None
    ) -> List[UserIntegrationConfig]:
        """Get user integration configurations using lazy smart defaults with overrides."""
        # Get user-specific configurations from database (only if they exist)
        stmt = (
            select(UserIntegrationConfig)
            .where(
                UserIntegrationConfig.user_id == user_id,
                UserIntegrationConfig.enabled == True,  # noqa: E712
            )
            .order_by(UserIntegrationConfig.priority.desc())
        )

        result = await db.execute(stmt)
        user_configs = result.scalars().all()
        user_configured_types = {
            config.integration_type.value for config in user_configs
        }

        # Prepare context from delivery request
        context = {}
        if request and request.template_variables:
            # Look for Slack channel information in template variables
            slack_channel = request.template_variables.get("slack_channel")
            if slack_channel:
                context["slack_channel"] = slack_channel
                logger.info(
                    "Found Slack channel in template variables",
                    user_id=user_id,
                    slack_channel=slack_channel,
                )

            # Look for Slack user ID in template variables
            slack_user_id = request.template_variables.get("slack_user_id")
            logger.info(
                "Checking template variables for slack_user_id",
                user_id=user_id,
                template_variables=request.template_variables,
                slack_user_id=slack_user_id,
            )
            if slack_user_id:
                context["slack_user_id"] = slack_user_id
                logger.info(
                    "Found Slack user ID in template variables",
                    user_id=user_id,
                    slack_user_id=slack_user_id,
                )
            else:
                logger.warning(
                    "No slack_user_id found in template variables",
                    user_id=user_id,
                    template_variables=request.template_variables,
                )

        # Get smart defaults for all enabled integrations (no database persistence)
        smart_defaults = await integration_defaults_service.get_smart_defaults(
            user_id, db=db, context=context
        )

        # Merge user configs with smart defaults
        final_configs = []

        # Start with user-specific configs (these override smart defaults)
        for user_config in user_configs:
            # For Slack configs, ensure they have channel information
            if user_config.integration_type == IntegrationType.SLACK:
                self._ensure_slack_config_has_identifiers(user_config, user_id)

            final_configs.append(user_config)

        # Add smart defaults for integrations not configured by user
        for integration_type, default_config in smart_defaults.items():
            if integration_type not in user_configured_types:
                # Create a temporary config object (not persisted to database)
                temp_config = UserIntegrationConfig(
                    user_id=user_id,
                    integration_type=default_config["integration_type"],
                    enabled=default_config["enabled"],
                    priority=default_config["priority"],
                    retry_count=default_config["retry_count"],
                    retry_delay_seconds=default_config["retry_delay_seconds"],
                    config=default_config["config"],
                )
                final_configs.append(temp_config)

        logger.info(
            "Final integration configuration (lazy approach)",
            user_id=user_id,
            total_configs=len(final_configs),
            user_configs=len(user_configs),
            smart_defaults=len(smart_defaults),
            integration_types=[
                config.integration_type.value for config in final_configs
            ],
        )

        return final_configs

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

        # Get user's integration configurations using smart defaults
        configs = await self._get_user_integration_configs(request.user_id, db, request)

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
        handler = self.handlers.get(config.integration_type)  # type: ignore[call-overload]
        if not handler:
            raise ValueError(
                f"No handler for integration type: {config.integration_type}"
            )

        # Render templates
        template_content = self.template_engine.render(
            integration_type=config.integration_type,  # type: ignore[arg-type]
            subject=request.subject,
            content=request.content,
            variables=request.template_variables,
        )

        # Create delivery log
        delivery_log = DeliveryLog(
            request_id=request.request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            integration_config_id=config.id,  # Will be None for smart defaults
            integration_type=get_enum_value(config.integration_type),
            subject=template_content.get("subject"),
            content=template_content.get("body"),
            max_attempts=config.retry_count,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        db.add(delivery_log)
        await db.commit()
        await db.refresh(delivery_log)

        # Attempt delivery
        try:
            delivery_log.first_attempt_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            delivery_log.last_attempt_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            delivery_log.attempts = 1  # type: ignore[assignment]

            integration_result = await handler.deliver(
                request, config, template_content
            )

            # Update delivery log
            delivery_log.status = integration_result.status.value
            delivery_log.integration_metadata = integration_result.metadata

            if integration_result.success:
                delivery_log.delivered_at = datetime.now(timezone.utc)  # type: ignore[assignment]
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
            delivery_log.status = DeliveryStatus.FAILED.value  # type: ignore[assignment]
            delivery_log.error_message = f"Handler error: {str(e)}"  # type: ignore[assignment]
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
            integration_config_id=config.id,  # Will be None for smart defaults
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


async def _integration_dispatcher_startup() -> None:
    """Custom startup logic for Integration Dispatcher."""
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

    # Initialize integration defaults
    logger.info("Initializing integration defaults...")
    try:
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            await integration_defaults_service.initialize_defaults(db)
        logger.info("Integration defaults initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize integration defaults", error=str(e))
        raise

    # Database migration is sufficient for startup validation
    logger.info("Integration Dispatcher startup validation completed")


# Create lifespan using shared utility with custom startup
def lifespan(app: FastAPI) -> Any:
    return create_shared_lifespan(
        service_name="integration-dispatcher",
        version=__version__,
        custom_startup=_integration_dispatcher_startup,
    )


# Initialize Integration Dispatcher
dispatcher = IntegrationDispatcher()

# Create FastAPI application
app = FastAPI(
    title="Self-Service Agent Integration Dispatcher",
    description="Multi-tenant Integration Dispatcher for Self-Service Agent Blueprint",
    version=__version__,
    lifespan=lifespan,
)

# Initialize services
slack_service = SlackService()
integration_defaults_service = IntegrationDefaultsService()


# Debug middleware to log all requests (only when DEBUG logging is enabled)
if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":

    @app.middleware("http")
    async def debug_requests(request: Request, call_next: Any) -> Any:
        logger.debug("Request received", method=request.method, path=request.url.path)
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


async def _integration_health_logic(db: AsyncSession) -> Dict[str, Any]:
    """Custom health logic for integration dispatcher."""
    # Convert integration handlers to the format expected by HealthChecker
    integration_handlers = {}
    for integration_type, handler in dispatcher.handlers.items():
        integration_name = get_enum_value(integration_type)
        integration_handlers[integration_name] = handler

    checker = HealthChecker("integration-dispatcher", __version__)
    result = await checker.perform_health_check(
        db=db,
        integration_handlers=integration_handlers,
    )

    return {
        "database_connected": result.database_connected,
        "integrations_available": result.integrations_available,
        "services": {
            "database": "connected" if result.database_connected else "disconnected",
            "integrations": f"{len(result.integrations_available)}/{len(dispatcher.handlers)} available",
        },
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint - lightweight without database dependency."""
    return {
        "status": "healthy",
        "service": "integration-dispatcher",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/detailed", response_model=HealthCheck)
async def detailed_health_check(
    db: AsyncSession = Depends(get_db_session_dependency),
) -> HealthCheck:
    """Detailed health check with database dependency for monitoring."""
    result = await create_health_check_endpoint(
        service_name="integration-dispatcher",
        version=__version__,
        db=db,
        custom_health_logic=_integration_health_logic,
    )

    return HealthCheck(
        status=result["status"],
        database_connected=result["database_connected"],
        integrations_available=result.get("integrations_available", []),
        services=result.get("services", {}),
    )


@app.post("/notifications")
async def handle_notification_event(
    request: Request,
    db: AsyncSession = Depends(get_db_session_dependency),
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
        # Note: Currently no notification handlers are implemented
        logger.info(
            "Notification event ignored",
            event_type=event_type,
            reason="no notification handlers implemented",
        )
        return {"status": "ignored", "reason": "no notification handlers implemented"}

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
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Handle incoming CloudEvents for delivery requests."""

    try:
        # Parse CloudEvent from request using shared utility
        event_data = await parse_cloudevent_from_request(request)

        # Extract CloudEvent fields with explicit handling
        event_id = event_data.get("id")
        event_type = event_data.get("type")
        event_source = event_data.get("source")

        # Log warning if critical fields are missing
        if not event_id:
            logger.warning("CloudEvent missing event ID")
            event_id = "unknown"
        if not event_type:
            logger.warning("CloudEvent missing event type")
            event_type = "unknown"
        if not event_source:
            logger.warning("CloudEvent missing event source")
            event_source = "unknown"

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
        if event_type != EventTypes.AGENT_RESPONSE_READY:
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
                "unknown",  # request_id
                "unknown",  # session_id
                "integration-dispatcher",
                "ignored",
                "unhandled event type",
            )
            return {"status": "ignored", "reason": "unhandled event type"}

        # Extract response data from CloudEvent (already parsed by parse_cloudevent_from_request)
        response_data = event_data.get("data", {})

        logger.debug(
            "CloudEvent data field contents",
            data_type=type(response_data),
            data_keys=(
                list(response_data.keys())
                if isinstance(response_data, dict)
                else "not_dict"
            ),
            data_preview=str(response_data)[:200] if response_data else "empty",
        )

        request_id = response_data.get("request_id")
        session_id = response_data.get("session_id")

        logger.info(
            "Parsing CloudEvent data",
            request_id=request_id,
            session_id=session_id,
            user_id=response_data.get("user_id"),
            agent_id=response_data.get("agent_id"),
        )

        # Create delivery request
        delivery_request = DeliveryRequest(
            request_id=response_data.get("request_id"),
            session_id=response_data.get("session_id"),
            user_id=response_data.get("user_id"),
            subject=response_data.get("subject"),
            content=response_data.get("content"),
            template_variables=response_data.get("template_variables", {}),
            agent_id=response_data.get("agent_id"),
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
        if delivery_request.request_id and delivery_request.session_id:
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
        else:
            logger.warning(
                "Cannot record processed event - missing request_id or session_id",
                request_id=delivery_request.request_id,
                session_id=delivery_request.session_id,
            )

        return await create_cloudevent_response(
            status="processed",
            message="CloudEvent processed successfully",
            details={
                "request_id": delivery_request.request_id,
                "dispatched_integrations": len(results),
                "results": results,
            },
        )

    except Exception as e:
        logger.error(
            "Failed to handle CloudEvent",
            error=str(e),
            event_type=event_type,
            event_data_keys=list(event_data.keys()) if "event_data" in locals() else [],
        )

        # ✅ RECORD FAILED EVENT PROCESSING
        request_id = event_data.get("request_id")
        session_id = event_data.get("session_id")

        if not request_id:
            logger.warning("CloudEvent missing request_id for error recording")
            request_id = "unknown"
        if not session_id:
            logger.warning("CloudEvent missing session_id for error recording")
            session_id = "unknown"

        await _record_processed_event(
            db,
            str(event_id),
            str(event_type),
            str(event_source),
            request_id,
            session_id,
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
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Handle direct delivery requests (for non-eventing mode)."""
    try:
        logger.debug("Direct delivery endpoint called")
        body = await request.body()
        delivery_data = json.loads(body)
        logger.debug("Delivery data received", delivery_data=delivery_data)

        logger.info(
            "Direct delivery request received",
            request_id=delivery_data.get("request_id"),
            session_id=delivery_data.get("session_id"),
            user_id=delivery_data.get("user_id"),
        )

        # Create delivery request from the payload using shared model
        from shared_models.models import DeliveryRequest

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
        logger.debug("Dispatch results", results=results)

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


# User Integration Configuration API
@app.get(
    "/api/v1/users/{user_id}/integrations",
    response_model=List[UserIntegrationConfigResponse],
)
async def get_user_integrations(
    user_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> List[UserIntegrationConfigResponse]:
    """Get user's integration configurations."""
    stmt = (
        select(UserIntegrationConfig)
        .where(UserIntegrationConfig.user_id == user_id)
        .order_by(UserIntegrationConfig.priority.desc())
    )

    result = await db.execute(stmt)
    configs = result.scalars().all()

    return [UserIntegrationConfigResponse.model_validate(config) for config in configs]


@app.post(
    "/api/v1/users/{user_id}/integrations", response_model=UserIntegrationConfigResponse
)
async def create_user_integration(
    user_id: str,
    config_data: UserIntegrationConfigCreate,
    db: AsyncSession = Depends(get_db_session_dependency),
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
        existing_config.enabled = config_data.enabled  # type: ignore[assignment]
        existing_config.config = config_data.config  # type: ignore[assignment]
        existing_config.priority = config_data.priority  # type: ignore[assignment]
        existing_config.retry_count = config_data.retry_count  # type: ignore[assignment]
        existing_config.retry_delay_seconds = config_data.retry_delay_seconds  # type: ignore[assignment]
        existing_config.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        # Ensure Slack configs have necessary identifiers
        if existing_config.integration_type == IntegrationType.SLACK:
            dispatcher._ensure_slack_config_has_identifiers(existing_config, user_id)

        await db.commit()
        await db.refresh(existing_config)
        return UserIntegrationConfigResponse.model_validate(existing_config)
    else:
        # Create new configuration
        config = UserIntegrationConfig(
            user_id=user_id,
            integration_type=config_data.integration_type,
            enabled=config_data.enabled,
            config=config_data.config,
            priority=config_data.priority,
            retry_count=config_data.retry_count,
            retry_delay_seconds=config_data.retry_delay_seconds,
        )

        # Ensure Slack configs have necessary identifiers
        if config.integration_type == IntegrationType.SLACK:
            dispatcher._ensure_slack_config_has_identifiers(config, user_id)

        db.add(config)
        await db.commit()
        await db.refresh(config)

        logger.info(
            "User integration configured",
            user_id=user_id,
            integration_type=get_enum_value(config_data.integration_type),
            enabled=config_data.enabled,
        )

        return UserIntegrationConfigResponse.model_validate(config)


@app.put(
    "/api/v1/users/{user_id}/integrations/{integration_type}",
    response_model=UserIntegrationConfigResponse,
)
async def update_user_integration(
    user_id: str,
    integration_type: IntegrationType,
    config_update: UserIntegrationConfigUpdate,
    db: AsyncSession = Depends(get_db_session_dependency),
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

    # Ensure Slack configs have necessary identifiers
    if config.integration_type == IntegrationType.SLACK:
        dispatcher._ensure_slack_config_has_identifiers(config, user_id)

    config.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    await db.commit()
    await db.refresh(config)

    return UserIntegrationConfigResponse.model_validate(config)


@app.delete("/api/v1/users/{user_id}/integrations/{integration_type}")
async def delete_user_integration(
    user_id: str,
    integration_type: IntegrationType,
    db: AsyncSession = Depends(get_db_session_dependency),
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


# Integration Defaults Management APIs
@app.get("/api/v1/integration-defaults")
async def get_integration_defaults(
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Get current integration defaults configuration from database (health-checked)."""
    defaults = await integration_defaults_service.get_database_integration_defaults(db)
    return {"default_integrations": defaults}


@app.get("/api/v1/users/{user_id}/integration-defaults")
async def get_user_integration_defaults(
    user_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, Any]:
    """Get user's effective integration configuration using integration defaults."""
    # Get user's overrides from database
    stmt = (
        select(UserIntegrationConfig)
        .where(UserIntegrationConfig.user_id == user_id)
        .order_by(UserIntegrationConfig.priority.desc())
    )

    result = await db.execute(stmt)
    user_configs = result.scalars().all()

    # Convert to override format
    user_overrides = {}
    for config in user_configs:
        user_overrides[config.integration_type.value] = {
            "enabled": config.enabled,
            "priority": config.priority,
            "retry_count": config.retry_count,
            "retry_delay_seconds": config.retry_delay_seconds,
            "config": config.config,
        }

    # Get effective configuration using integration defaults
    effective_configs = await integration_defaults_service.get_user_integrations(
        user_id, user_overrides
    )

    return {
        "user_id": user_id,
        "user_overrides": user_overrides,
        "effective_configs": effective_configs,
        "using_integration_defaults": len(user_configs) == 0,
    }


@app.post("/api/v1/users/{user_id}/integration-defaults/reset")
async def reset_user_to_integration_defaults(
    user_id: str,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Dict[str, str]:
    """Reset user to integration defaults by removing all custom configurations."""
    # Delete all user-specific configurations
    stmt = select(UserIntegrationConfig).where(UserIntegrationConfig.user_id == user_id)

    result = await db.execute(stmt)
    configs = result.scalars().all()

    for config in configs:
        await db.delete(config)

    await db.commit()

    logger.info(
        "User reset to integration defaults",
        user_id=user_id,
        deleted_configs=len(configs),
    )

    return {
        "message": f"User {user_id} reset to integration defaults",
        "deleted_configs": str(len(configs)),
    }


@app.get("/api/v1/users/{user_id}/deliveries", response_model=List[DeliveryLogResponse])
async def get_user_deliveries(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session_dependency),
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

    return [DeliveryLogResponse.model_validate(delivery) for delivery in deliveries]


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


# Slack Integration Endpoints


@app.post("/slack/events")
async def handle_slack_events(
    request: Request, db: AsyncSession = Depends(get_db_session_dependency)
) -> Dict[str, Any]:
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

            if event_type in ("message", "app_mention"):
                await slack_service.handle_message_event(
                    event, data.get("team_id"), db, data.get("event_id")
                )

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
async def handle_slack_interactive(request: Request) -> Dict[str, Any]:
    """Handle Slack interactive components (buttons, etc.)."""
    try:
        body = await request.body()
        headers = request.headers

        # Verify signature
        timestamp = headers.get("x-slack-request-timestamp", "")
        signature = headers.get("x-slack-signature", "")

        if not slack_service.verify_slack_signature(body, timestamp, signature):
            logger.warning("Invalid Slack signature")
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
) -> Dict[str, Any]:
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
    error_message: str | None = None,
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
