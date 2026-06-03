"""Shared models and schemas for Self-Service Agent Blueprint."""

__version__ = "0.1.0"

# Export advisory lock (request-manager, integration-dispatcher)
from .advisory_lock import with_advisory_lock
from .channel_behavior import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    CHANNEL_REGISTRY,
    PER_TICKET_CHANNEL_BEHAVIOR_SEED,
    WIRED_DISPATCHER_HANDLER_TYPES,
    WIRED_DISPATCHER_ONLY,
    WIRED_REQUEST_MANAGER_INGRESS_TYPES,
    WIRED_RM_AND_DISPATCHER,
    WIRED_RM_INGRESS_ONLY,
    ChannelDefinition,
    build_integration_metadata_with_policy,
    channel_behavior_allow_db_override,
    channel_uses_ticket_user_id_suffix,
    code_default_channel_behavior,
    delivery_context_for_forward,
    delivery_context_from_session_metadata,
    effective_entry_agent_id,
    effective_router_agent_id,
    filter_configs_for_delivery_binding,
    get_channel_definition,
    is_per_ticket_integration,
    is_ticket_delivery_eligible,
    is_ticket_delivery_integration,
    looks_like_per_ticket_session_id,
    per_ticket_integration_types,
    policy_from_integration_metadata,
    policy_needs_ticket_context,
    resolve_channel_behavior,
    resolve_channel_behavior_sync,
    session_per_integration_type_enabled,
    should_filter_sessions_by_integration_type,
    ticket_delivery_eligible_types,
    ticket_delivery_integration_types,
    validate_channel_behavior_policy,
)
from .channel_behavior_session import (
    SessionPinScopeMismatchError,
    TicketIdRequiredError,
    create_per_user_session_direct,
    find_active_per_user_sessions,
    parse_ticket_id,
    parse_ticket_id_from_metadata,
    prepare_new_session_metadata,
    resolve_ticket_scoped_session,
    row_excluded_from_unified_pool,
    should_filter_lookup_by_integration_type,
    touch_active_session,
    validate_explicit_session_pin,
)

# Export channel behavior policy (types in channel_policy_types to avoid registry import cycle)
from .channel_policy_types import (
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    DeliveryBinding,
    SessionScope,
)

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
    get_db_utc_now,
)

# Export CloudEvent utilities
from .events import (
    CloudEventBuilder,
    CloudEventSender,
    EventTypes,
    agent_response_event_id,
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

# Export outbox (Step 0.25)
from .outbox import (
    SOURCE_SERVICE_INTEGRATION_DISPATCHER,
    insert_outbox_event,
    mark_outbox_failed,
    mark_outbox_published,
    reset_outbox_for_retry,
)

# Export request log ordering utilities
from .request_log import (
    get_request_created_at,
    has_earlier_pending_or_processing,
)

# Export security utilities
from .security import verify_slack_signature

# Export session lock (agent cross-pod serialization)
from .session_lock import (
    acquire_agent_session_lock,
    release_agent_session_lock,
    session_id_to_lock_key,
)

# Export session management
from .session_manager import (
    BaseSessionManager,
    get_or_create_ticket_session,
    initial_current_agent_id_for_integration,
    ticket_session_id,
)
from .session_schemas import SessionCreate, SessionResponse, SessionUpdate

# Export user utilities
from .user_utils import (
    get_or_create_canonical_user,
    is_uuid,
    resolve_canonical_user_id,
)

# Export utilities
from .utils import (
    generate_fallback_user_id,
    get_enum_value,
    json_value_as_dict,
    normalize_zammad_rest_api_base,
    zammad_rest_authorization_headers,
    zammad_rest_json_headers,
)

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
    "json_value_as_dict",
    "normalize_zammad_rest_api_base",
    "zammad_rest_authorization_headers",
    "zammad_rest_json_headers",
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
    "get_db_utc_now",
    "acquire_agent_session_lock",
    "release_agent_session_lock",
    "session_id_to_lock_key",
    "with_advisory_lock",
    "get_request_created_at",
    "has_earlier_pending_or_processing",
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
    "agent_response_event_id",
    "CHANNEL_BEHAVIOR_SNAPSHOT_KEY",
    "CHANNEL_REGISTRY",
    "ChannelBehaviorPolicy",
    "ChannelBehaviorValidationError",
    "ChannelDefinition",
    "DeliveryBinding",
    "SessionScope",
    "build_integration_metadata_with_policy",
    "channel_behavior_allow_db_override",
    "channel_uses_ticket_user_id_suffix",
    "code_default_channel_behavior",
    "get_channel_definition",
    "delivery_context_for_forward",
    "delivery_context_from_session_metadata",
    "filter_configs_for_delivery_binding",
    "is_per_ticket_integration",
    "is_ticket_delivery_eligible",
    "is_ticket_delivery_integration",
    "looks_like_per_ticket_session_id",
    "per_ticket_integration_types",
    "PER_TICKET_CHANNEL_BEHAVIOR_SEED",
    "ticket_delivery_integration_types",
    "create_per_user_session_direct",
    "find_active_per_user_sessions",
    "parse_ticket_id_from_metadata",
    "resolve_ticket_scoped_session",
    "effective_entry_agent_id",
    "effective_router_agent_id",
    "policy_from_integration_metadata",
    "policy_needs_ticket_context",
    "resolve_channel_behavior",
    "resolve_channel_behavior_sync",
    "session_per_integration_type_enabled",
    "should_filter_sessions_by_integration_type",
    "ticket_delivery_eligible_types",
    "validate_channel_behavior_policy",
    "WIRED_RM_AND_DISPATCHER",
    "WIRED_DISPATCHER_HANDLER_TYPES",
    "WIRED_DISPATCHER_ONLY",
    "WIRED_REQUEST_MANAGER_INGRESS_TYPES",
    "WIRED_RM_INGRESS_ONLY",
    "SessionPinScopeMismatchError",
    "TicketIdRequiredError",
    "parse_ticket_id",
    "prepare_new_session_metadata",
    "row_excluded_from_unified_pool",
    "should_filter_lookup_by_integration_type",
    "touch_active_session",
    "validate_explicit_session_pin",
    "BaseSessionManager",
    "get_or_create_ticket_session",
    "ticket_session_id",
    "initial_current_agent_id_for_integration",
    "SessionCreate",
    "SessionResponse",
    "SessionUpdate",
    "SOURCE_SERVICE_INTEGRATION_DISPATCHER",
    "insert_outbox_event",
    "mark_outbox_failed",
    "mark_outbox_published",
    "reset_outbox_for_retry",
]
