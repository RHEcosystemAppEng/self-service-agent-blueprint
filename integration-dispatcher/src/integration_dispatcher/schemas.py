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


class DeliveryLogResponse(BaseModel):
    """Schema for delivery log response."""

    id: int
    request_id: str
    session_id: str
    user_id: str
    integration_type: IntegrationType
    subject: Optional[str]
    content: str
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


class HealthCheck(BaseModel):
    """Health check response schema."""

    status: str
    database_connected: bool
    integrations_available: List[str]
    services: Dict[str, str]


# ErrorResponse is now imported from shared_models.models
