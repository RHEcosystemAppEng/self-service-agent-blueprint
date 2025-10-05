"""
ServiceNow API client for laptop refresh requests.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict

import requests

from .auth import AuthManager
from .models import (
    ApiKeyConfig,
    AuthConfig,
    AuthType,
    BasicAuthConfig,
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
            "sysparm_quantity": 1,
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

    def _get(self, endpoint, params=None):
        """Internal method for making GET requests to ServiceNow API."""
        full_url = f"{self.config.instance_url}{endpoint}"
        headers = self.auth_manager.get_headers()
        headers["Accept"] = "application/json"

        try:
            response = requests.get(
                full_url, headers=headers, params=params, timeout=self.config.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow API Error: {e}")
            return None

    def get_user_by_email(self, email: str) -> Dict[str, Any]:
        """
        Fetches a user record from ServiceNow by email.

        Args:
            email: The email address to search for.

        Returns:
            Dictionary containing the result of the operation with success, message, and user data.
        """
        if not email:
            return {"success": False, "message": "Email parameter is required"}

        # Build query parameters following ServiceNow MCP pattern
        params = {
            "sysparm_query": f"email={email}",
            "sysparm_limit": "1",
            "sysparm_display_value": "true",
        }

        try:
            data = self._get("/api/now/table/sys_user", params)

            if not data:
                return {
                    "success": False,
                    "message": "Failed to connect to ServiceNow API",
                }

            if data.get("result") and len(data["result"]) > 0:
                user_data = data["result"][0]
                return {
                    "success": True,
                    "message": "User found successfully",
                    "user": user_data,
                }
            else:
                logger.error(f"User with email '{email}' not found in ServiceNow")
                return {
                    "success": False,
                    "message": f"User with email '{email}' not found",
                }

        except Exception as e:
            logger.error(f"Failed to get user by email: {e}")
            return {
                "success": False,
                "message": f"Failed to get user by email: {str(e)}",
            }

    def get_computer_by_user_sys_id(self, user_sys_id: str) -> Dict[str, Any]:
        """
        Fetches computer records assigned to a specific user sys_id.

        Args:
            user_sys_id: The sys_id of the user to search for computers.

        Returns:
            Dictionary containing the result of the operation with success, message, and computers data.
        """
        if not user_sys_id:
            return {"success": False, "message": "User sys_id parameter is required"}

        # Build query parameters following ServiceNow MCP pattern
        params = {
            "sysparm_query": f"assigned_to={user_sys_id}",
            "sysparm_display_value": "true",
        }

        try:
            data = self._get("/api/now/table/cmdb_ci_computer", params)

            if not data:
                return {
                    "success": False,
                    "message": "Failed to connect to ServiceNow API",
                }

            if data.get("result"):
                computers = data["result"]
                return {
                    "success": True,
                    "message": f"Found {len(computers)} computer(s) for user",
                    "computers": computers,
                }
            else:
                logger.info(f"No computers found for user sys_id '{user_sys_id}'")
                return {
                    "success": True,
                    "message": "No computers found for user",
                    "computers": [],
                }

        except Exception as e:
            logger.error(f"Failed to get computers for user sys_id: {e}")
            return {"success": False, "message": f"Failed to get computers: {str(e)}"}

    def get_employee_laptop_info(self, employee_email: str) -> str:
        """
        Orchestrates fetching user and their assigned computer details from ServiceNow.

        Args:
            employee_email: The email address of the employee.

        Returns:
            Formatted string containing employee and laptop information, or error message.
        """
        if not employee_email:
            return "Error: Employee email is required"

        # Step 1: Get user data
        user_result = self.get_user_by_email(employee_email)
        if not user_result["success"]:
            return f"Error: {user_result['message']}"

        user_data = user_result["user"]

        # Step 2: Get computer data
        user_sys_id = user_data.get("sys_id")
        if not user_sys_id:
            return f"Error: User {user_data.get('name', 'Unknown')} has no sys_id in ServiceNow"

        computers_result = self.get_computer_by_user_sys_id(user_sys_id)
        if not computers_result["success"]:
            return f"Error: {computers_result['message']}"

        computers_data = computers_result["computers"]
        if not computers_data:
            return f"User {user_data.get('name')} found, but no laptops are assigned to them in ServiceNow."

        # Step 3: Format response for multiple laptops
        try:
            # Handle nested objects safely for user data
            location_value = "N/A"
            if isinstance(user_data.get("location"), dict):
                location_value = user_data.get("location", {}).get(
                    "display_value", "N/A"
                )
            elif user_data.get("location"):
                location_value = str(user_data.get("location"))

            # Start building response with user info
            laptop_info = f"""Employee Name: {user_data.get("name", "N/A")}
Employee ID: {user_data.get("sys_id", "N/A")}
Employee Location: {location_value}
Total Laptops: {len(computers_data)}

"""

            # Add information for each laptop
            for i, computer_data in enumerate(computers_data, 1):
                # Handle nested objects safely for each computer
                model_value = "N/A"
                if isinstance(computer_data.get("model_id"), dict):
                    model_value = computer_data.get("model_id", {}).get(
                        "display_value", "N/A"
                    )
                elif computer_data.get("model_id"):
                    model_value = str(computer_data.get("model_id"))

                # Calculate warranty status for this laptop
                warranty_expiry = computer_data.get("warranty_expiration", "N/A")
                warranty_status = "Unknown"
                if warranty_expiry and warranty_expiry != "N/A":
                    try:
                        # Try multiple date formats
                        for date_format in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                            try:
                                expiry_date = datetime.strptime(
                                    warranty_expiry, date_format
                                )
                                current_date = datetime.now()
                                warranty_status = (
                                    "Active"
                                    if expiry_date > current_date
                                    else "Expired"
                                )
                                break
                            except ValueError:
                                continue
                    except Exception as e:
                        logger.warning(
                            f"Could not parse warranty expiry date '{warranty_expiry}': {e}"
                        )
                        warranty_status = "Unknown"

                laptop_info += f"""Laptop {i}:
  Model: {model_value}
  Serial Number: {computer_data.get("serial_number", "N/A")}
  Purchase Date: {computer_data.get("purchase_date", computer_data.get("assigned", "N/A"))}
  Warranty Expiry: {warranty_expiry}
  Warranty Status: {warranty_status}

"""

            return laptop_info.strip()

        except Exception as e:
            logger.error(f"Error formatting laptop info: {e}")
            return f"Error: Failed to format laptop information - {str(e)}"
