"""Shared models and schemas for Self-Service Agent Blueprint."""

__version__ = "0.1.0"

# Export agent utilities
from .agent_types import (
    AgentMapping,
    create_agent_mapping,
    is_agent_name,
    is_agent_uuid,
)

# Export CloudEvent utilities
from .cloudevent_utils import (
    create_cloudevent_response,
    parse_cloudevent_from_request,
    validate_cloudevent_headers,
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

# Export error utilities
from .errors import (
    AgentError,
    DatabaseError,
    ErrorResponse,
    IntegrationError,
    ServiceError,
    SessionError,
    create_error_response,
    create_forbidden_error,
    create_not_found_error,
    create_unauthorized_error,
    create_validation_error,
    handle_agent_error,
    handle_database_error,
    handle_generic_error,
    handle_integration_error,
    handle_service_error,
    handle_session_error,
)

# Export CloudEvent utilities
from .events import (
    CloudEventBuilder,
    CloudEventProcessor,
    CloudEventSender,
    CloudEventValidator,
    EventTypes,
    create_request_event,
    create_response_event,
    extract_event_context,
    validate_event_type,
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

# Export utilities
from .utils import generate_fallback_user_id, get_enum_value

__all__ = [
    "verify_slack_signature",
    "create_health_check_dependency",
    "create_health_check_endpoint",
    "create_shared_lifespan",
    "create_standard_fastapi_app",
    "parse_cloudevent_from_request",
    "validate_cloudevent_headers",
    "create_cloudevent_response",
    "get_enum_value",
    "generate_fallback_user_id",
    "DatabaseConfig",
    "DatabaseHealthChecker",
    "DatabaseManager",
    "DatabaseUtils",
    "get_database_manager",
    "get_db_config",
    "get_db_session",
    "get_db_session_dependency",
    "AgentMapping",
    "create_agent_mapping",
    "is_agent_name",
    "is_agent_uuid",
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
    "CloudEventProcessor",
    "CloudEventSender",
    "CloudEventValidator",
    "EventTypes",
    "create_request_event",
    "create_response_event",
    "extract_event_context",
    "validate_event_type",
    "AgentError",
    "DatabaseError",
    "ErrorResponse",
    "IntegrationError",
    "ServiceError",
    "SessionError",
    "create_error_response",
    "create_forbidden_error",
    "create_not_found_error",
    "create_unauthorized_error",
    "create_validation_error",
    "handle_agent_error",
    "handle_database_error",
    "handle_generic_error",
    "handle_integration_error",
    "handle_service_error",
    "handle_session_error",
]
