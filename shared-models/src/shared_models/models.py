"""Consolidated database models for all services."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import JSON, Boolean, Column
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin

# Export Base for use in other modules
__all__ = [
    "Base",
    "IntegrationType",
    "SessionStatus",
    "DeliveryStatus",
    "RequestSession",
    "RequestLog",
    "UserIntegrationConfig",
    "IntegrationDefaultConfig",
    "IntegrationTemplate",
    "DeliveryLog",
    "ProcessedEvent",
    "IntegrationCredential",
    "UserIntegrationMapping",
    "AgentResponse",
    "NormalizedRequest",
    "DeliveryRequest",
    "ErrorResponse",
]


# Enums used across services
class IntegrationType(str, Enum):
    """Integration types for both request sources and delivery channels."""

    SLACK = "SLACK"
    WEB = "WEB"
    CLI = "CLI"
    TOOL = "TOOL"
    EMAIL = "EMAIL"
    SMS = "SMS"
    WEBHOOK = "WEBHOOK"
    TEAMS = "TEAMS"
    DISCORD = "DISCORD"
    TEST = "TEST"


class SessionStatus(str, Enum):
    """Session status for request management."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class DeliveryStatus(str, Enum):
    """Delivery status for integration messages."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    EXPIRED = "EXPIRED"


# Request Manager Models
class RequestSession(Base, TimestampMixin):
    """User conversation sessions."""

    __tablename__ = "request_sessions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )
    status: Column[SessionStatus] = Column(
        SQLEnum(SessionStatus), default=SessionStatus.ACTIVE.value, nullable=False
    )

    # Session context
    channel_id = Column(String(255))  # Slack channel, Teams channel, etc.
    thread_id = Column(String(255))  # Thread/conversation ID
    external_session_id = Column(String(255))  # External platform session ID

    # Agent tracking
    current_agent_id = Column(String(255))  # Currently assigned agent
    conversation_thread_id = Column(
        String(255)
    )  # LangGraph conversation thread ID or LlamaStack session ID

    # Session metadata
    integration_metadata = Column(JSON, default=dict)
    user_context = Column(JSON, default=dict)  # User context from platform
    conversation_context = Column(JSON, default=dict)  # Conversation state

    # Session statistics
    total_requests = Column(Integer, default=0, nullable=False)
    last_request_id = Column(String(36))  # Most recent request ID
    last_request_at = Column(TIMESTAMP(timezone=True))
    expires_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    request_logs = relationship(
        "RequestLog", back_populates="session", cascade="all, delete-orphan"
    )


class RequestLog(Base, TimestampMixin):
    """Log of all requests processed."""

    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), unique=True, nullable=False, index=True)
    session_id = Column(
        String(36),
        ForeignKey("request_sessions.session_id"),
        nullable=False,
        index=True,
    )

    # Request details
    request_type = Column(String(50), nullable=False)  # "slack", "web", "cli", "tool"
    request_content = Column(Text, nullable=False)
    normalized_request = Column(JSON)  # Normalized request structure

    # Agent processing
    agent_id = Column(String(255))
    processing_time_ms = Column(Integer)

    # Response details
    response_content = Column(Text)
    response_metadata = Column(JSON, default=dict)

    # CloudEvent tracking
    cloudevent_id = Column(String(36))
    cloudevent_type = Column(String(100))

    # Timing
    completed_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    session = relationship("RequestSession", back_populates="request_logs")


# Integration Dispatcher Models
class UserIntegrationConfig(Base, TimestampMixin):
    """Per-user integration configuration."""

    __tablename__ = "user_integration_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )
    enabled = Column(Boolean, default=True, nullable=False)

    # Integration-specific configuration
    config = Column(JSON, nullable=False, default=dict)

    # Delivery preferences
    priority = Column(Integer, default=0, nullable=False)  # Higher = more important
    retry_count = Column(Integer, default=3, nullable=False)
    retry_delay_seconds = Column(Integer, default=60, nullable=False)

    # Metadata
    created_by = Column(String(255))  # Who configured this integration

    # Relationships
    delivery_logs = relationship(
        "DeliveryLog", back_populates="integration_config", cascade="all, delete-orphan"
    )

    # Ensure one config per user per integration type
    __table_args__ = (
        UniqueConstraint("user_id", "integration_type", name="uq_user_integration"),
    )


class IntegrationDefaultConfig(Base, TimestampMixin):
    """Default integration configurations for new users."""

    __tablename__ = "integration_default_configs"

    id = Column(Integer, primary_key=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False, unique=True
    )
    enabled = Column(Boolean, default=True, nullable=False)

    # Integration-specific configuration
    config = Column(JSON, nullable=False, default=dict)

    # Delivery preferences
    priority = Column(Integer, default=0, nullable=False)  # Higher = more important
    retry_count = Column(Integer, default=3, nullable=False)
    retry_delay_seconds = Column(Integer, default=60, nullable=False)

    # Metadata
    created_by = Column(String(255), default="system")  # System-generated defaults


class IntegrationTemplate(Base, TimestampMixin):
    """Templates for different integration types."""

    __tablename__ = "integration_templates"

    id = Column(Integer, primary_key=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )
    template_name = Column(String(100), nullable=False)

    # Template content
    subject_template = Column(Text)  # For email/notification title
    body_template = Column(Text, nullable=False)

    # Template variables and metadata
    required_variables = Column(JSON, default=list)  # List of required template vars
    optional_variables = Column(JSON, default=list)  # List of optional template vars

    # Template configuration
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Unique template per integration type and name
    __table_args__ = (
        UniqueConstraint(
            "integration_type", "template_name", name="uq_integration_template"
        ),
    )


class DeliveryLog(Base, TimestampMixin):
    """Log of integration message deliveries."""

    __tablename__ = "delivery_logs"

    id = Column(Integer, primary_key=True)

    # Request/session context
    request_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)

    # Integration details
    integration_config_id = Column(
        Integer,
        ForeignKey("user_integration_configs.id", ondelete="CASCADE"),
        nullable=True,  # Allow null for smart defaults (lazy approach)
    )
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )

    # Message content
    subject = Column(Text)
    content = Column(Text, nullable=False)
    template_used = Column(String(100))

    # Delivery tracking
    status: Column[DeliveryStatus] = Column(
        SQLEnum(DeliveryStatus), default=DeliveryStatus.PENDING.value, nullable=False
    )
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)

    # Timing
    first_attempt_at = Column(TIMESTAMP(timezone=True))
    last_attempt_at = Column(TIMESTAMP(timezone=True))
    delivered_at = Column(TIMESTAMP(timezone=True))
    expires_at = Column(TIMESTAMP(timezone=True))  # When to stop retrying

    # Error tracking
    error_message = Column(Text)
    error_details = Column(JSON)

    # Integration-specific metadata
    integration_metadata = Column(JSON, default=dict)  # Channel IDs, message IDs, etc.

    # Relationships
    integration_config = relationship(
        "UserIntegrationConfig", back_populates="delivery_logs"
    )


class ProcessedEvent(Base, TimestampMixin):
    """Track processed CloudEvents to prevent duplicate processing."""

    __tablename__ = "processed_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(255), nullable=False, unique=True)  # ce-id
    event_type = Column(String(255), nullable=False)  # ce-type
    event_source = Column(String(255), nullable=False)  # ce-source
    request_id = Column(String(255), nullable=True)  # For correlation
    session_id = Column(String(255), nullable=True)  # For correlation
    processed_by = Column(String(100), nullable=False)  # service name
    processing_result = Column(String(50), nullable=False)  # success/error/skipped
    error_message = Column(Text, nullable=True)

    # Index for fast lookups
    __table_args__ = (
        Index("ix_processed_events_event_id", "event_id"),
        Index("ix_processed_events_request_id", "request_id"),
        Index("ix_processed_events_created_at", "created_at"),
    )


class IntegrationCredential(Base, TimestampMixin):
    """Secure storage for integration credentials."""

    __tablename__ = "integration_credentials"

    id = Column(Integer, primary_key=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )
    credential_name = Column(
        String(100), nullable=False
    )  # e.g., "slack_bot_token", "smtp_password"

    # Encrypted credential value (encrypt before storing)
    encrypted_value = Column(Text, nullable=False)

    # Metadata
    description = Column(Text)
    created_by = Column(String(255))

    # Unique credential per integration type and name
    __table_args__ = (
        UniqueConstraint(
            "integration_type", "credential_name", name="uq_integration_credential"
        ),
    )


class UserIntegrationMapping(Base, TimestampMixin):
    """Mapping between user emails and integration-specific user IDs."""

    __tablename__ = "user_integration_mappings"

    id = Column(Integer, primary_key=True)
    user_email = Column(String(255), nullable=False, index=True)
    integration_type: Column[IntegrationType] = Column(
        SQLEnum(IntegrationType), nullable=False
    )
    integration_user_id = Column(String(255), nullable=False)  # e.g., Slack user ID

    # Validation metadata
    last_validated_at = Column(TIMESTAMP(timezone=True))
    validation_attempts = Column(Integer, default=0, nullable=False)
    last_validation_error = Column(Text)

    # Metadata
    created_by = Column(String(255), default="system")

    # Ensure one mapping per email per integration type
    __table_args__ = (
        UniqueConstraint(
            "user_email", "integration_type", name="uq_user_integration_mapping"
        ),
        Index(
            "ix_user_integration_mapping_email_type", "user_email", "integration_type"
        ),
    )


# Shared Pydantic models for inter-service communication
class AgentResponse(BaseModel):
    """Shared model for agent responses across all services."""

    request_id: str
    session_id: str
    user_id: str
    agent_id: Optional[str]
    content: str
    response_type: str = Field(default="message")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    processing_time_ms: Optional[int] = None
    requires_followup: bool = Field(default=False)
    followup_actions: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Shared Pydantic models for inter-service communication
class NormalizedRequest(BaseModel):
    """Normalized internal request format used across all services."""

    request_id: str = Field(..., description="Unique request identifier")
    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., min_length=1, max_length=255)
    integration_type: IntegrationType
    request_type: str = Field(..., max_length=100)
    content: str = Field(..., min_length=1)

    # Integration-specific context
    integration_context: Dict[str, Any] = Field(default_factory=dict)
    user_context: Dict[str, Any] = Field(default_factory=dict)

    # Agent routing
    target_agent_id: Optional[str] = Field(None, max_length=255)
    requires_routing: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("integration_type", mode="before")
    @classmethod
    def normalize_integration_type(cls, v: Any) -> Any:
        """Convert integration_type to uppercase for case-insensitive input."""
        if isinstance(v, str):
            return IntegrationType(v.upper())
        return v

    class Config:
        """Pydantic config."""

        use_enum_values = True


class DeliveryRequest(BaseModel):
    """Shared model for delivery requests across services."""

    request_id: str
    session_id: str
    user_id: str
    subject: Optional[str] = None
    content: str
    template_variables: Dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = None
    priority_override: Optional[int] = None


class ErrorResponse(BaseModel):
    """Shared error response schema across all services."""

    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code")
    request_id: Optional[str] = Field(None, description="Request ID if available")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )
