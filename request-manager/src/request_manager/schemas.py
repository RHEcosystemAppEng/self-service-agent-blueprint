"""Pydantic schemas for request/response validation."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator
from shared_models.models import IntegrationType


class BaseRequest(BaseModel):
    """Base request schema."""

    integration_type: IntegrationType
    user_id: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    request_type: str = Field(default="message", max_length=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("integration_type", mode="before")
    @classmethod
    def normalize_integration_type(cls, v: Any) -> Any:
        """Convert integration_type to uppercase for case-insensitive input."""
        if isinstance(v, str):
            return IntegrationType(v.upper())
        return v


class SlackRequest(BaseRequest):
    """Slack-specific request schema."""

    integration_type: IntegrationType = IntegrationType.SLACK
    channel_id: Optional[str] = Field(None, max_length=255)  # Optional for DM requests
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


# NormalizedRequest is now imported from shared_models.models


# Session schemas moved to shared-models


class HealthCheck(BaseModel):
    """Health check response schema."""

    status: str = Field(default="healthy")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = Field(default="0.1.0")
    database_connected: bool = Field(default=False)
    services: Dict[str, str] = Field(default_factory=dict)


# ErrorResponse is now imported from shared_models.models
