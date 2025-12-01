"""Shared models and schemas for Self-Service Agent Blueprint."""

__version__ = "0.1.0"

# Export CloudEvent utilities
from .cloudevent_utils import (
    CloudEventHandler,
    create_cloudevent_response,
    parse_cloudevent_from_request,
)
from .database import (
    DatabaseConfig,
    DatabaseHealthChecker,
    DatabaseManager,
    DatabaseUtils,
    get_database_manager,
    get_db_config,
    get_db_session,
    get_db_session_dependency,
)

# Export CloudEvent utilities
from .events import (
    CloudEventBuilder,
    CloudEventSender,
    EventTypes,
)

# Export FastAPI utilities
from .fastapi_utils import (
    create_health_check_dependency,
    create_health_check_endpoint,
    create_shared_lifespan,
    create_standard_fastapi_app,
)

# Export health utilities
from .health import HealthChecker, HealthCheckResult, simple_health_check

# Export logging utilities
from .logging import (
    LoggingConfig,
    ServiceLogger,
    configure_logging,
    get_service_logger,
    log_database_operation,
    log_error,
    log_health_check,
    log_integration_event,
    log_request,
    log_response,
)

# Export security utilities
from .security import verify_slack_signature

# Export user utilities
from .user_utils import (
    get_or_create_canonical_user,
    is_uuid,
    resolve_canonical_user_id,
)

# Export utilities
from .utils import generate_fallback_user_id, get_enum_value

__all__ = [
    "verify_slack_signature",
    "create_health_check_dependency",
    "create_health_check_endpoint",
    "create_shared_lifespan",
    "create_standard_fastapi_app",
    "parse_cloudevent_from_request",
    "create_cloudevent_response",
    "get_enum_value",
    "generate_fallback_user_id",
    "get_or_create_canonical_user",
    "is_uuid",
    "resolve_canonical_user_id",
    "CloudEventHandler",
    "DatabaseConfig",
    "DatabaseHealthChecker",
    "DatabaseManager",
    "DatabaseUtils",
    "get_database_manager",
    "get_db_config",
    "get_db_session",
    "get_db_session_dependency",
    "HealthChecker",
    "HealthCheckResult",
    "simple_health_check",
    "LoggingConfig",
    "ServiceLogger",
    "configure_logging",
    "get_service_logger",
    "log_database_operation",
    "log_error",
    "log_health_check",
    "log_integration_event",
    "log_request",
    "log_response",
    "CloudEventBuilder",
    "CloudEventSender",
    "EventTypes",
]
