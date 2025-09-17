"""Pydantic schemas for request/response validation."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator
from shared_db.models import (
    AgentResponse,
    IntegrationType,
    NormalizedRequest,
    SessionStatus,
)


class BaseRequest(BaseModel):
    """Base request schema."""

    integration_type: IntegrationType
    user_id: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    request_type: str = Field(default="message", max_length=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("integration_type", mode="before")
    @classmethod
    def normalize_integration_type(cls, v):
        """Convert integration_type to uppercase for case-insensitive input."""
        if isinstance(v, str):
            return IntegrationType(v.upper())
        return v


class SlackRequest(BaseRequest):
    """Slack-specific request schema."""

    integration_type: IntegrationType = IntegrationType.SLACK
    channel_id: str = Field(..., min_length=1, max_length=255)
    thread_id: Optional[str] = Field(None, max_length=255)
    slack_user_id: str = Field(..., min_length=1, max_length=255)
    slack_team_id: str = Field(..., min_length=1, max_length=255)


class WebRequest(BaseRequest):
    """Web interface request schema."""

    integration_type: IntegrationType = IntegrationType.WEB
    session_token: Optional[str] = Field(None, max_length=500)
    client_ip: Optional[str] = Field(None, max_length=45)
    user_agent: Optional[str] = Field(None, max_length=500)


class CLIRequest(BaseRequest):
    """CLI request schema."""

    integration_type: IntegrationType = IntegrationType.CLI
    cli_session_id: Optional[str] = Field(None, max_length=255)
    command_context: Dict[str, Any] = Field(default_factory=dict)


class ToolRequest(BaseRequest):
    """Tool-generated request schema."""

    integration_type: IntegrationType = IntegrationType.TOOL
    tool_id: str = Field(..., min_length=1, max_length=255)
    tool_instance_id: Optional[str] = Field(None, max_length=255)
    trigger_event: str = Field(..., min_length=1, max_length=255)
    tool_context: Dict[str, Any] = Field(default_factory=dict)


# NormalizedRequest is now imported from shared_db.models


class SessionCreate(BaseModel):
    """Schema for creating a new session."""

    user_id: str = Field(..., min_length=1, max_length=255)
    integration_type: IntegrationType
    integration_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_context: Dict[str, Any] = Field(default_factory=dict)

    # Integration-specific fields
    channel_id: Optional[str] = Field(None, max_length=255)
    thread_id: Optional[str] = Field(None, max_length=255)
    external_session_id: Optional[str] = Field(None, max_length=255)

    @field_validator("integration_type", mode="before")
    @classmethod
    def normalize_integration_type(cls, v):
        """Convert integration_type to uppercase for case-insensitive input."""
        if isinstance(v, str):
            return IntegrationType(v.upper())
        return v


class SessionResponse(BaseModel):
    """Schema for session information."""

    session_id: str
    user_id: str
    integration_type: IntegrationType
    status: SessionStatus
    current_agent_id: Optional[str]
    llama_stack_session_id: Optional[str]

    # Context
    conversation_context: Dict[str, Any]
    integration_metadata: Dict[str, Any]
    user_context: Dict[str, Any]

    # Statistics
    total_requests: int
    last_request_id: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_request_at: Optional[datetime] = None

    class Config:
        """Pydantic config."""

        from_attributes = True
        use_enum_values = True


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    status: Optional[SessionStatus] = None
    current_agent_id: Optional[str] = None
    llama_stack_session_id: Optional[str] = None
    conversation_context: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None


class CloudEventRequest(BaseModel):
    """Schema for CloudEvent requests."""

    specversion: str = Field(default="1.0")
    type: str = Field(..., description="Event type")
    source: str = Field(..., description="Event source")
    id: str = Field(..., description="Event ID")
    time: Optional[datetime] = None
    subject: Optional[str] = None
    datacontenttype: str = Field(default="application/json")
    data: NormalizedRequest = Field(..., description="Event data")


class CloudEventResponse(BaseModel):
    """Schema for CloudEvent responses."""

    specversion: str = Field(default="1.0")
    type: str = Field(..., description="Event type")
    source: str = Field(..., description="Event source")
    id: str = Field(..., description="Event ID")
    time: Optional[datetime] = None
    subject: Optional[str] = None
    datacontenttype: str = Field(default="application/json")
    data: AgentResponse = Field(..., description="Event data")


class HealthCheck(BaseModel):
    """Health check response schema."""

    status: str = Field(default="healthy")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = Field(default="0.1.0")
    database_connected: bool = Field(default=False)
    services: Dict[str, str] = Field(default_factory=dict)


# ErrorResponse is now imported from shared_db.models
