"""
ServiceNow API client for laptop refresh requests.
"""

import logging
import os
from typing import Any, Dict

import requests

from .auth import AuthManager
from .models import (
    ApiKeyConfig,
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    CatalogResponse,
    OAuthConfig,
    OpenServiceNowLaptopRefreshRequestParams,
    ServerConfig,
)

logger = logging.getLogger(__name__)


class ServiceNowClient:
    """
    ServiceNow API client for making requests to ServiceNow instance.
    """

    def __init__(self):
        """
        Initialize the ServiceNow client with configuration from environment variables.
        """
        self.config = self._load_config_from_env()
        self.auth_manager = AuthManager(self.config.auth, self.config.instance_url)

    def _load_config_from_env(self) -> ServerConfig:
        """
        Load configuration from environment variables.

        Returns:
            ServerConfig: Configuration loaded from environment variables.

        Raises:
            ValueError: If required environment variables are missing.
        """
        instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
        if not instance_url:
            raise ValueError("SERVICENOW_INSTANCE_URL environment variable is required")

        auth_type = os.getenv("SERVICENOW_AUTH_TYPE", "basic").lower()

        if auth_type == "basic":
            username = os.getenv("SERVICENOW_USERNAME")
            password = os.getenv("SERVICENOW_PASSWORD")
            if not username or not password:
                raise ValueError(
                    "SERVICENOW_USERNAME and SERVICENOW_PASSWORD are required for basic auth"
                )

            auth_config = AuthConfig(
                type=AuthType.BASIC,
                basic=BasicAuthConfig(username=username, password=password),
            )

        elif auth_type == "oauth":
            client_id = os.getenv("SERVICENOW_CLIENT_ID")
            client_secret = os.getenv("SERVICENOW_CLIENT_SECRET")
            username = os.getenv("SERVICENOW_USERNAME")
            password = os.getenv("SERVICENOW_PASSWORD")

            if not client_id or not client_secret:
                raise ValueError(
                    "SERVICENOW_CLIENT_ID and SERVICENOW_CLIENT_SECRET are required for OAuth"
                )

            auth_config = AuthConfig(
                type=AuthType.OAUTH,
                oauth=OAuthConfig(
                    client_id=client_id,
                    client_secret=client_secret,
                    username=username or "",
                    password=password or "",
                    token_url=os.getenv("SERVICENOW_TOKEN_URL"),
                ),
            )

        elif auth_type == "api_key":
            api_key = os.getenv("SERVICENOW_API_KEY")
            if not api_key:
                raise ValueError("SERVICENOW_API_KEY is required for API key auth")

            auth_config = AuthConfig(
                type=AuthType.API_KEY,
                api_key=ApiKeyConfig(
                    api_key=api_key,
                    header_name=os.getenv(
                        "SERVICENOW_API_KEY_HEADER", "X-ServiceNow-API-Key"
                    ),
                ),
            )

        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")

        return ServerConfig(
            instance_url=instance_url,
            auth=auth_config,
            debug=os.getenv("SERVICENOW_DEBUG", "false").lower() == "true",
            timeout=int(os.getenv("SERVICENOW_TIMEOUT", "30")),
        )

    def open_laptop_refresh_request(
        self, params: OpenServiceNowLaptopRefreshRequestParams
    ) -> Dict[str, Any]:
        """
        Open a ServiceNow laptop refresh request.

        Args:
            params: Parameters for the laptop refresh request.

        Returns:
            Dictionary containing the result of the operation.
        """
        logger.info("Opening ServiceNow laptop refresh request")

        # Build the API URL with the hardcoded laptop refresh ID
        laptop_refresh_id = os.getenv(
            "SERVICENOW_LAPTOP_REFRESH_ID", "1d3eae4f93232210eead74418bba10f4"
        )
        url = f"{self.config.instance_url}/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now"

        # Prepare request body
        body = {
            "sysparm_quantity": params.sysparm_quantity,
            "variables": {
                "laptop_choices": params.laptop_choices,
                "who_is_this_request_for": params.who_is_this_request_for,
            },
        }

        # Make the API request
        headers = self.auth_manager.get_headers()

        try:
            response = requests.post(
                url, headers=headers, json=body, timeout=self.config.timeout
            )
            response.raise_for_status()

            # Process the response
            result = response.json()

            return {
                "success": True,
                "message": "Successfully opened laptop refresh request",
                "data": result,
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error opening laptop refresh request: {str(e)}")
            return {
                "success": False,
                "message": f"Error opening laptop refresh request: {str(e)}",
                "data": None,
            }
