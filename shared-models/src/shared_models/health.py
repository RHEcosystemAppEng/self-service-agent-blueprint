"""Shared health check utilities for all services."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class HealthCheckResult:
    """Health check result with detailed status information."""

    def __init__(
        self,
        status: str = "healthy",
        service_name: str = "unknown",
        version: str = "0.1.0",
        database_connected: bool = False,
        integrations_available: List[str] = None,
        integration_errors: Dict[str, str] = None,
        services: Dict[str, str] = None,
    ):
        self.status = status
        self.service_name = service_name
        self.version = version
        self.database_connected = database_connected
        self.integrations_available = integrations_available or []
        self.integration_errors = integration_errors or {}
        self.services = services or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status,
            "service": self.service_name,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "database_connected": self.database_connected,
            "integrations_available": self.integrations_available,
            "integration_errors": self.integration_errors,
            "services": self.services,
        }


class HealthChecker:
    """Shared health check utility for all services."""

    def __init__(self, service_name: str, version: str = "0.1.0"):
        self.service_name = service_name
        self.version = version

    async def check_database(self, db: AsyncSession) -> bool:
        """Check database connectivity."""
        try:
            await db.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    async def check_integrations(
        self, integration_handlers: Dict[str, Any] = None
    ) -> tuple[List[str], Dict[str, str]]:
        """Check integration handlers health."""
        if not integration_handlers:
            return [], {}

        integrations_available = []
        integration_errors = {}

        for integration_name, handler in integration_handlers.items():
            try:
                if hasattr(handler, "health_check"):
                    # Check if integration is configured before running health check
                    is_configured = await self._is_integration_configured(handler)

                    if not is_configured:
                        # Integration not configured - this is normal, not an error
                        logger.debug(
                            "Integration not configured - skipping health check",
                            integration=integration_name,
                        )
                        continue

                    # Integration is configured - run health check
                    is_healthy = await handler.health_check()
                    if is_healthy:
                        integrations_available.append(integration_name)
                        logger.debug(
                            "Integration health check passed",
                            integration=integration_name,
                        )
                    else:
                        # This is an actual failure, not just not configured
                        # Exception: TEST integration failure when disabled is not an error
                        if integration_name == "TEST":
                            logger.debug(
                                "TEST integration disabled - not considered an error",
                                integration=integration_name,
                            )
                        else:
                            integration_errors[integration_name] = "Health check failed"
                            logger.warning(
                                "Integration health check failed",
                                integration=integration_name,
                            )
                else:
                    # If no health check method, assume healthy
                    integrations_available.append(integration_name)
            except Exception as e:
                integration_errors[integration_name] = str(e)
                logger.error(
                    "Integration health check error",
                    integration=integration_name,
                    error=str(e),
                )

        return integrations_available, integration_errors

    async def perform_health_check(
        self,
        db: Optional[AsyncSession] = None,
        integration_handlers: Dict[str, Any] = None,
        additional_checks: Dict[str, callable] = None,
    ) -> HealthCheckResult:
        """Perform comprehensive health check."""
        logger.debug("Starting health check", service=self.service_name)

        # Check database
        database_connected = False
        if db:
            database_connected = await self.check_database(db)

        # Check integrations
        integrations_available, integration_errors = await self.check_integrations(
            integration_handlers
        )

        # Run additional custom checks
        services = {}
        if additional_checks:
            for service_name, check_func in additional_checks.items():
                try:
                    result = await check_func()
                    services[service_name] = "healthy" if result else "unhealthy"
                except Exception as e:
                    services[service_name] = f"error: {str(e)}"
                    logger.error(
                        "Additional health check failed",
                        service=service_name,
                        error=str(e),
                    )

        # Determine overall status
        status = "healthy"
        if not database_connected:
            status = "degraded"
        elif integration_errors:
            # Only mark as degraded if there are actual integration errors
            # (configured integrations that failed health checks)
            # Note: Unconfigured integrations (like EMAIL without SMTP) are not errors
            status = "degraded"

        # If database is connected and no integration errors, we're healthy
        # even if some integrations are intentionally disabled/unconfigured

        result = HealthCheckResult(
            status=status,
            service_name=self.service_name,
            version=self.version,
            database_connected=database_connected,
            integrations_available=integrations_available,
            integration_errors=integration_errors,
            services=services,
        )

        logger.debug(
            "Health check completed",
            service=self.service_name,
            status=status,
            database_connected=database_connected,
            integrations_count=len(integrations_available),
            errors_count=len(integration_errors),
        )

        return result

    async def _is_integration_configured(self, handler: Any) -> bool:
        """Check if an integration is properly configured.

        This method checks if the integration has the required configuration
        before running health checks. Returns True if configured, False if not.
        """
        try:
            # Check if handler has a method to check configuration
            if hasattr(handler, "is_configured"):
                return await handler.is_configured()

            # For integrations without explicit configuration check,
            # try to determine if they're configured by checking common attributes
            if hasattr(handler, "smtp_username") and hasattr(handler, "smtp_password"):
                # Email integration - check if credentials are provided
                return bool(handler.smtp_username and handler.smtp_password)

            if hasattr(handler, "bot_token"):
                # Slack integration - check if bot token is provided
                return bool(handler.bot_token)

            if hasattr(handler, "webhook_url"):
                # Webhook integration - check if URL is provided
                return bool(handler.webhook_url)

            # For other integrations, assume they're configured if they exist
            # This allows integrations like TEST to always be considered configured
            return True

        except Exception as e:
            logger.debug(
                "Error checking integration configuration",
                error=str(e),
            )
            # If we can't determine configuration status, assume not configured
            return False


# Convenience function for simple health checks
async def simple_health_check(
    service_name: str,
    version: str = "0.1.0",
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Simple health check for basic services."""
    checker = HealthChecker(service_name, version)
    result = await checker.perform_health_check(db=db)
    return result.to_dict()
