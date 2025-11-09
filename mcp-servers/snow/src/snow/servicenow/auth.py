"""
Authentication manager for the ServiceNow MCP server.
"""

import logging
from typing import Dict

from .models import AuthConfig, AuthType

logger = logging.getLogger(__name__)


class AuthManager:
    """
    Authentication manager for ServiceNow API.

    This class handles authentication with the ServiceNow API using
    API key authentication.
    """

    def __init__(self, config: AuthConfig, instance_url: str | None = None):
        """
        Initialize the authentication manager.

        Args:
            config: Authentication configuration.
            instance_url: ServiceNow instance URL.
        """
        self.config = config
        self.instance_url = instance_url

    def get_headers(self) -> Dict[str, str]:
        """
        Get the authentication headers for API requests.

        Returns:
            Dict[str, str]: Headers to include in API requests.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.config.type == AuthType.API_KEY:
            if not self.config.api_key:
                raise ValueError("API key configuration is required")

            headers[self.config.api_key.header_name] = self.config.api_key.api_key

        return headers
