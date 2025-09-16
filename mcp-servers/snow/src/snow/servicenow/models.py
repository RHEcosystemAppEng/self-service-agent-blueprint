"""
ServiceNow API models and data structures.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    """Authentication types supported by the ServiceNow client."""

    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "api_key"


class BasicAuthConfig(BaseModel):
    """Configuration for basic authentication."""

    username: str
    password: str


class OAuthConfig(BaseModel):
    """Configuration for OAuth authentication."""

    client_id: str
    client_secret: str
    username: str
    password: str
    token_url: Optional[str] = None


class ApiKeyConfig(BaseModel):
    """Configuration for API key authentication."""

    api_key: str
    header_name: str = "X-ServiceNow-API-Key"


class AuthConfig(BaseModel):
    """Authentication configuration."""

    type: AuthType
    basic: Optional[BasicAuthConfig] = None
    oauth: Optional[OAuthConfig] = None
    api_key: Optional[ApiKeyConfig] = None


class ServerConfig(BaseModel):
    """Server configuration."""

    instance_url: str
    auth: AuthConfig
    debug: bool = False
    timeout: int = 30

    @property
    def api_url(self) -> str:
        """Get the API URL for the ServiceNow instance."""
        return f"{self.instance_url}/api/now"


class OpenServiceNowLaptopRefreshRequestParams(BaseModel):
    """Parameters for opening a ServiceNow laptop refresh request."""

    laptop_choices: str = Field(
        "lenovo_think_pad_p_16_gen_2",
        description="Laptop choice for the refresh request",
    )
    who_is_this_request_for: str = Field(
        ..., description="User ID for whom this request is being made"
    )


class CatalogResponse(BaseModel):
    """Response from catalog operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Message describing the result")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
