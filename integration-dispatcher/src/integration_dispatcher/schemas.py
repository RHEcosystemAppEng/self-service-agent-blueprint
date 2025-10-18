"""Pydantic schemas for Integration Dispatcher."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from shared_models.models import DeliveryStatus, IntegrationType


class UserIntegrationConfigCreate(BaseModel):
    """Schema for creating user integration configuration."""

    integration_type: IntegrationType
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    retry_count: int = 3
    retry_delay_seconds: int = 60

    @field_validator("integration_type", mode="before")
    @classmethod
    def normalize_integration_type(cls, v: Any) -> Any:
        """Convert integration_type to uppercase for case-insensitive input."""
        if isinstance(v, str):
            return IntegrationType(v.upper())
        return v


class UserIntegrationConfigUpdate(BaseModel):
    """Schema for updating user integration configuration."""

    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    retry_count: Optional[int] = None
    retry_delay_seconds: Optional[int] = None


class UserIntegrationConfigResponse(BaseModel):
    """Schema for user integration configuration response."""

    id: int
    user_id: str
    integration_type: IntegrationType
    enabled: bool
    config: Dict[str, Any]
    priority: int
    retry_count: int
    retry_delay_seconds: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IntegrationTemplateCreate(BaseModel):
    """Schema for creating integration template."""

    integration_type: IntegrationType
    template_name: str
    subject_template: Optional[str] = None
    body_template: str
    required_variables: List[str] = Field(default_factory=list)
    optional_variables: List[str] = Field(default_factory=list)
    is_default: bool = False


class IntegrationTemplateResponse(BaseModel):
    """Schema for integration template response."""

    id: int
    integration_type: IntegrationType
    template_name: str
    subject_template: Optional[str]
    body_template: str
    required_variables: List[str]
    optional_variables: List[str]
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeliveryLogResponse(BaseModel):
    """Schema for delivery log response."""

    id: int
    request_id: str
    session_id: str
    user_id: str
    integration_type: IntegrationType
    subject: Optional[str]
    content: str
    template_used: Optional[str]
    status: DeliveryStatus
    attempts: int
    max_attempts: int
    created_at: datetime
    first_attempt_at: Optional[datetime]
    last_attempt_at: Optional[datetime]
    delivered_at: Optional[datetime]
    expires_at: Optional[datetime]
    error_message: Optional[str]
    integration_metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class SlackConfig(BaseModel):
    """Slack integration configuration."""

    channel_id: Optional[str] = None  # Default channel, can be overridden
    workspace_id: Optional[str] = None
    thread_replies: bool = True  # Reply in thread vs new message
    mention_user: bool = False  # @mention the user
    include_agent_info: bool = True  # Include which agent responded


class EmailConfig(BaseModel):
    """Email integration configuration."""

    email_address: str
    display_name: Optional[str] = None
    format: str = "html"  # "html" or "text"
    include_signature: bool = True
    reply_to: Optional[str] = None


class SMSConfig(BaseModel):
    """SMS integration configuration."""

    phone_number: str
    country_code: str = "+1"
    max_length: int = 160  # Split long messages
    include_short_link: bool = True  # Link to full response


class WebhookConfig(BaseModel):
    """Webhook integration configuration."""

    url: str
    method: str = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    verify_ssl: bool = True
    auth_type: Optional[str] = None  # "bearer", "basic", "api_key"
    auth_config: Dict[str, str] = Field(default_factory=dict)


class HealthCheck(BaseModel):
    """Health check response schema."""

    status: str
    database_connected: bool
    integrations_available: List[str]
    services: Dict[str, str]


# ErrorResponse is now imported from shared_models.models
