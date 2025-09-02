"""FastAPI utilities for shared patterns across services."""

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Dict, Optional

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_database_manager, get_db_session_dependency
from .health import HealthChecker
from .logging import configure_logging

logger = configure_logging("fastapi-utils")


async def create_health_check_endpoint(
    service_name: str,
    version: str,
    db: AsyncSession,
    additional_checks: Optional[Dict[str, Callable]] = None,
    custom_health_logic: Optional[Callable[[AsyncSession], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create a standardized health check endpoint for any service.

    Args:
        service_name: Name of the service (e.g., "request-manager")
        version: Version of the service
        db: Database session (provided by FastAPI dependency injection)
        additional_checks: Dict of additional health check functions
        custom_health_logic: Custom health check logic that takes db session

    Returns:
        Health check response dictionary
    """
    checker = HealthChecker(service_name, version)

    try:
        # Perform standard health checks
        result = await checker.perform_health_check(
            db=db, additional_checks=additional_checks
        )

        # Apply custom health logic if provided
        custom_status = {}
        if custom_health_logic:
            try:
                custom_status = await custom_health_logic(db)
            except Exception as e:
                logger.error("Custom health check failed", error=str(e))
                custom_status = {"custom_health": "failed", "error": str(e)}

        # Combine results
        response = {
            "status": result.status,
            "service": service_name,
            "version": version,
            "database_connected": result.database_connected,
            "services": result.services,
            **custom_status,
        }

        return response

    except Exception as e:
        logger.error("Health check failed", service=service_name, error=str(e))
        return {
            "status": "unhealthy",
            "service": service_name,
            "version": version,
            "error": str(e),
        }


def create_health_check_dependency(
    service_name: str,
    version: str,
    additional_checks: Optional[Dict[str, Callable]] = None,
    custom_health_logic: Optional[Callable[[AsyncSession], Dict[str, Any]]] = None,
) -> Callable:
    """
    Create a health check dependency function for FastAPI endpoints.

    Args:
        service_name: Name of the service
        version: Version of the service
        additional_checks: Dict of additional health check functions
        custom_health_logic: Custom health check logic

    Returns:
        FastAPI dependency function
    """

    async def health_check_dependency(
        db: AsyncSession = Depends(get_db_session_dependency),
    ) -> Dict[str, Any]:
        return await create_health_check_endpoint(
            service_name=service_name,
            version=version,
            db=db,
            additional_checks=additional_checks,
            custom_health_logic=custom_health_logic,
        )

    return health_check_dependency


@asynccontextmanager
async def create_shared_lifespan(
    service_name: str,
    version: str,
    migration_timeout: int = 300,
    custom_startup: Optional[Callable] = None,
    custom_shutdown: Optional[Callable] = None,
    service_client_init: bool = True,
) -> AsyncGenerator[None, None]:
    """
    Create a standardized FastAPI lifespan manager for services.

    Args:
        service_name: Name of the service (e.g., "request-manager")
        version: Version of the service
        migration_timeout: Timeout for database migration waiting
        custom_startup: Custom startup function to call after standard startup
        custom_shutdown: Custom shutdown function to call before standard shutdown
        service_client_init: Whether to initialize shared service clients

    Yields:
        None (standard lifespan pattern)
    """
    # Startup
    logger.info(f"Starting {service_name}", version=version)

    # Wait for database migration to complete
    db_manager = get_database_manager()
    try:
        migration_ready = await db_manager.wait_for_migration(timeout=migration_timeout)
        if not migration_ready:
            raise Exception("Database migration did not complete within timeout")
        logger.info("Database migration verified and ready")
    except Exception as e:
        logger.error("Failed to verify database migration", error=str(e))
        raise

    # Initialize service clients if requested
    if service_client_init:
        try:
            from shared_clients import initialize_service_clients

            # Get service URLs from environment
            agent_service_url = os.getenv(
                "AGENT_SERVICE_URL", "http://self-service-agent-agent-service:80"
            )
            request_manager_url = os.getenv(
                "REQUEST_MANAGER_URL",
                "http://self-service-agent-request-manager:8080",
            )
            integration_dispatcher_url = os.getenv(
                "INTEGRATION_DISPATCHER_URL",
                "http://self-service-agent-integration-dispatcher:8080",
            )

            initialize_service_clients(
                agent_service_url=agent_service_url,
                request_manager_url=request_manager_url,
                integration_dispatcher_url=integration_dispatcher_url,
            )
            logger.debug("Initialized service clients")
        except ImportError:
            logger.warning(
                "shared_clients not available, skipping service client initialization"
            )
        except Exception as e:
            logger.error("Failed to initialize service clients", error=str(e))

    # Call custom startup function if provided
    if custom_startup:
        try:
            await custom_startup()
            logger.info("Custom startup completed")
        except Exception as e:
            logger.error("Custom startup failed", error=str(e))
            raise

    logger.info(f"{service_name} startup completed")

    yield

    # Shutdown
    logger.info(f"Shutting down {service_name}")

    # Call custom shutdown function if provided
    if custom_shutdown:
        try:
            await custom_shutdown()
            logger.info("Custom shutdown completed")
        except Exception as e:
            logger.error("Custom shutdown failed", error=str(e))

    # Close service clients if they were initialized
    if service_client_init:
        try:
            from shared_clients import cleanup_service_clients

            await cleanup_service_clients()
            logger.info("Service clients cleaned up")
        except ImportError:
            pass  # shared_clients not available
        except Exception as e:
            logger.error("Failed to cleanup service clients", error=str(e))

    # Close database connections
    await db_manager.close()
    logger.info(f"{service_name} shutdown completed")


def create_standard_fastapi_app(
    service_name: str,
    version: str,
    description: str,
    lifespan_func: Optional[Callable] = None,
    cors_origins: list = None,
) -> FastAPI:
    """
    Create a standardized FastAPI application with common configuration.

    Args:
        service_name: Name of the service
        version: Version of the service
        description: Description of the service
        lifespan_func: Custom lifespan function (if None, uses shared lifespan)
        cors_origins: CORS origins list (default: ["*"])

    Returns:
        Configured FastAPI application
    """
    if cors_origins is None:
        cors_origins = ["*"]

    # Use shared lifespan if none provided
    if lifespan_func is None:
        lifespan_func = create_shared_lifespan(service_name, version)

    # Create FastAPI app
    app = FastAPI(
        title=f"Self-Service Agent {service_name.replace('-', ' ').title()}",
        description=description,
        version=version,
        lifespan=lifespan_func,
    )

    # Add CORS middleware
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info(f"Created FastAPI app for {service_name}")
    return app
