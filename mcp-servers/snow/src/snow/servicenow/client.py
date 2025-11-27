"""
ServiceNow API client for laptop refresh requests.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from shared_models import configure_logging
from snow.servicenow.utils import _calculate_laptop_age

from .auth import AuthManager
from .models import (
    ApiKeyConfig,
    AuthConfig,
    AuthType,
    OpenServiceNowLaptopRefreshRequestParams,
    ServerConfig,
)

logger = configure_logging("snow-mcp-server")


class ServiceNowClient:
    """
    ServiceNow API client for making requests to ServiceNow instance.
    """

    def __init__(
        self,
        api_token: str | None = None,
        laptop_refresh_id: str | None = None,
        laptop_request_limits: int | None = None,
        laptop_avoid_duplicates: bool = False,
    ) -> None:
        """
        Initialize the ServiceNow client with API token and laptop refresh ID.

        Args:
            api_token: ServiceNow API token from request header (SERVICE_NOW_TOKEN).
                       This is required and must be provided for authentication.
            laptop_refresh_id: ServiceNow catalog item ID for laptop refresh requests.
                              This is required and should be provided at server startup.
            laptop_request_limits: Maximum number of open laptop requests allowed per user.
                                 If None, no limits are enforced. Defaults to None.
            laptop_avoid_duplicates: Whether to avoid creating duplicate laptop requests
                                   for the same laptop model. Defaults to False.

        Raises:
            ValueError: If api_token or laptop_refresh_id is not provided.
        """
        if not api_token:
            raise ValueError("ServiceNow API token is required.")
        if not laptop_refresh_id:
            raise ValueError("ServiceNow laptop refresh ID is required.")

        self.laptop_refresh_id = laptop_refresh_id
        self.laptop_request_limits = laptop_request_limits
        self.laptop_avoid_duplicates = laptop_avoid_duplicates
        self.config = self._load_config(api_token=api_token)
        self.auth_manager = AuthManager(self.config.auth, self.config.instance_url)

    def _load_config(self, api_token: str) -> ServerConfig:
        """
        Load configuration using API token.

        Args:
            api_token: ServiceNow API token from request header.

        Returns:
            ServerConfig: Configuration loaded with API token.

        Raises:
            ValueError: If required environment variables are missing.
        """
        instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
        if not instance_url:
            raise ValueError("SERVICENOW_INSTANCE_URL environment variable is required")

        auth_config = AuthConfig(
            type=AuthType.API_KEY,
            api_key=ApiKeyConfig(
                api_key=api_token,
                header_name=os.getenv("SERVICENOW_API_KEY_HEADER", "x-sn-apikey"),
            ),
        )

        return ServerConfig(
            instance_url=instance_url,
            auth=auth_config,
            debug=os.getenv("SERVICENOW_DEBUG", "false").lower() == "true",
            timeout=int(os.getenv("SERVICENOW_TIMEOUT", "30")),
        )

    def _has_existing_request_for_laptop_model(
        self, existing_requests: List[Dict[str, Any]], laptop_model: str
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if there's already an open request for the same laptop model.

        Args:
            existing_requests: List of existing open requests for the user.
            laptop_model: The laptop model to check for.

        Returns:
            Tuple of (bool, Optional[Dict]):
            - True if existing request found, False otherwise
            - The existing request data if found, None otherwise
        """
        # If avoid_duplicates is disabled, skip the duplicate check entirely
        if not self.laptop_avoid_duplicates:
            return False, None

        for request in existing_requests:
            # Extract laptop choice from request - using new sc_req_item format
            # The API returns variables.laptop_choices as a direct field
            existing_laptop_choice = request.get("variables.laptop_choices", "")

            if existing_laptop_choice == laptop_model:
                # Get the REQ number from the parent request
                req_number = request.get("request.number", "N/A")
                logger.info(
                    "Found existing open request for same laptop model",
                    existing_request_number=req_number,
                    laptop_model=laptop_model,
                )
                # Return a modified request object with REQ number in the number field
                # to maintain interface compatibility with calling code
                modified_request = request.copy()
                modified_request["number"] = req_number
                return True, modified_request

        return False, None

    def _would_exceed_request_limit(
        self, existing_requests: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if adding a new request would exceed the request limits.

        Args:
            existing_requests: List of existing open requests for the user.

        Returns:
            True if adding a new request would exceed the limit, False otherwise.
            If laptop_request_limits is None, no limits are enforced and this returns False.
        """
        # If no limits are configured, allow unlimited requests
        if self.laptop_request_limits is None:
            return False

        if len(existing_requests) >= self.laptop_request_limits:
            logger.warning(
                "Request limit exceeded",
                existing_requests=len(existing_requests),
                limit=self.laptop_request_limits,
            )
            return True
        return False

    def open_laptop_refresh_request(
        self, params: OpenServiceNowLaptopRefreshRequestParams
    ) -> Dict[str, Any]:
        """
        Open a ServiceNow laptop refresh request.
        Before opening, checks for existing open requests to avoid duplicates and enforce limits.

        Args:
            params: Parameters for the laptop refresh request.

        Returns:
            Dictionary containing the result of the operation.
        """
        logger.info("Opening ServiceNow laptop refresh request")

        # Step 1: Check for existing open requests for this user
        user_sys_id = params.who_is_this_request_for
        logger.info("Checking for existing open requests", user_sys_id=user_sys_id)

        existing_requests_result = self.get_open_laptop_requests_for_user(user_sys_id)
        if not existing_requests_result["success"]:
            return existing_requests_result

        existing_requests = existing_requests_result["requests"]
        logger.info(
            "Found existing open request(s)", existing_requests=len(existing_requests)
        )

        # Step 2: Check if there's already an open request for the same laptop model
        current_laptop_model = params.laptop_choices
        has_existing_model_request, existing_request = (
            self._has_existing_request_for_laptop_model(
                existing_requests, current_laptop_model
            )
        )
        if has_existing_model_request:
            assert (
                existing_request is not None
            ), "existing_request should not be None when has_existing_model_request is True"
            return {
                "success": True,
                "message": f"Existing open request found for the same laptop model: {existing_request.get('number', 'N/A')}",
                "data": {"existing_request": existing_request},
                "existing_ticket": True,
            }

        # Step 3: Check if adding a new request would exceed the limits
        if self._would_exceed_request_limit(existing_requests):
            return {
                "success": False,
                "message": f"Cannot open new laptop request. User already has {len(existing_requests)} open request(s), which meets or exceeds the limit of {self.laptop_request_limits}.",
                "data": {
                    "existing_requests": existing_requests,
                    "limit": self.laptop_request_limits,
                },
            }

        # Step 4: Proceed with creating a new request
        logger.info("Proceeding to create new laptop request")

        # Use the laptop refresh ID that was provided at initialization
        logger.info(
            "Using ServiceNow laptop refresh catalog item ID",
            laptop_refresh_id=self.laptop_refresh_id,
        )
        url = f"{self.config.instance_url}/api/sn_sc/servicecatalog/items/{self.laptop_refresh_id}/order_now"

        # Prepare request body with proper structure for order_now endpoint
        # ServiceNow expects variables as a nested object under "variables" key
        body = {
            "sysparm_quantity": 1,
            "variables": {
                "laptop_choices": params.laptop_choices,
                "who_is_this_request_for": params.who_is_this_request_for,
            },
        }

        # Make the API request
        headers = self.auth_manager.get_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        # Debug logging - log the request being sent
        logger.info("Sending request to ServiceNow", url=url)
        logger.info("Request body", body=body)

        try:
            response = requests.post(
                url, headers=headers, json=body, timeout=self.config.timeout
            )

            # Debug logging - log the response
            logger.info("Response received", status_code=response.status_code)
            logger.info("Response body", body=response.text)

            response.raise_for_status()

            # Process the response
            result = response.json()

            # Log the complete response for debugging
            logger.info("Full ServiceNow response", response=result)

            return {
                "success": True,
                "message": "Successfully opened laptop refresh request",
                "data": result,
                "existing_ticket": False,
            }

        except requests.exceptions.RequestException as e:
            logger.error(
                "Error opening laptop refresh request",
                error=str(e),
                error_type=type(e).__name__,
            )
            return {
                "success": False,
                "message": f"Error opening laptop refresh request: {str(e)}",
                "data": None,
            }

    def _get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Internal method for making GET requests to ServiceNow API."""
        full_url = f"{self.config.instance_url}{endpoint}"
        headers = self.auth_manager.get_headers()
        headers["Accept"] = "application/json"

        try:
            response = requests.get(
                full_url, headers=headers, params=params, timeout=self.config.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, dict) else None

        except requests.exceptions.RequestException as e:
            logger.error(
                "ServiceNow API Error", error=str(e), error_type=type(e).__name__
            )
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
            "sysparm_fields": "sys_id,name,email,user_name,location,active",
        }

        try:
            data = self._get("/api/now/table/sys_user", params)

            if not data:
                return {
                    "success": False,
                    "message": "Failed to connect to ServiceNow API",
                }

            if data and data.get("result") and len(data["result"]) > 0:
                user_data = data["result"][0]
                return {
                    "success": True,
                    "message": "User found successfully",
                    "user": user_data,
                }
            else:
                logger.error("User not found in ServiceNow", email=email)
                return {
                    "success": False,
                    "message": f"User with email '{email}' not found",
                }

        except Exception as e:
            logger.error(
                "Failed to get user by email",
                email=email,
                error=str(e),
                error_type=type(e).__name__,
            )
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
            "sysparm_fields": "sys_id,name,asset_tag,serial_number,model_id,assigned_to,purchase_date,warranty_expiration,install_status,operational_status",
        }

        try:
            data = self._get("/api/now/table/cmdb_ci_computer", params)

            if not data:
                return {
                    "success": False,
                    "message": "Failed to connect to ServiceNow API",
                }

            if data and data.get("result"):
                computers = data["result"]
                return {
                    "success": True,
                    "message": f"Found {len(computers)} computer(s) for user",
                    "computers": computers,
                }
            else:
                logger.info("No computers found for user", user_sys_id=user_sys_id)
                return {
                    "success": True,
                    "message": "No computers found for user",
                    "computers": [],
                }

        except Exception as e:
            logger.error(
                "Failed to get computers for user",
                user_sys_id=user_sys_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {"success": False, "message": f"Failed to get computers: {str(e)}"}

    def get_employee_laptop_info(self, employee_identifier: str) -> str:
        """
        Orchestrates fetching user and their assigned computer details from ServiceNow.

        Note: This method currently only supports email-based lookups via the ServiceNow API.

        Args:
            employee_identifier: The email address of the employee.

        Returns:
            Formatted string containing employee and laptop information, or error message.
        """
        if not employee_identifier:
            return "Error: Employee identifier is required"

        # Step 1: Get user data (currently only supports email lookup)
        user_result = self.get_user_by_email(employee_identifier)
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

        # Step 3: Format response using first laptop only (matching mock data format)
        try:
            # Handle nested objects safely for user data
            location_value = "N/A"
            if isinstance(user_data.get("location"), dict):
                location_value = user_data.get("location", {}).get(
                    "display_value", "N/A"
                )
            elif user_data.get("location"):
                location_value = str(user_data.get("location"))

            # Convert location to uppercase
            if location_value and location_value != "N/A":
                location_value = location_value.upper()

            # Get first laptop only
            computer_data = computers_data[0]

            # Handle nested objects safely for laptop model
            model_value = "N/A"
            if isinstance(computer_data.get("model_id"), dict):
                model_value = computer_data.get("model_id", {}).get(
                    "display_value", "N/A"
                )
            elif computer_data.get("model_id"):
                model_value = str(computer_data.get("model_id"))

            # Get purchase date and normalize format to YYYY-MM-DD
            purchase_date = computer_data.get(
                "purchase_date", computer_data.get("assigned", "N/A")
            )
            normalized_purchase_date = purchase_date
            if purchase_date and purchase_date != "N/A":
                # Try to normalize date format
                for date_format in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        parsed_date = datetime.strptime(purchase_date, date_format)
                        normalized_purchase_date = parsed_date.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue

            # Calculate laptop age
            laptop_age = _calculate_laptop_age(normalized_purchase_date)

            # Get warranty expiry and normalize format to YYYY-MM-DD
            warranty_expiry = computer_data.get("warranty_expiration", "N/A")
            normalized_warranty_expiry = warranty_expiry
            warranty_status = "Unknown"

            if warranty_expiry and warranty_expiry != "N/A":
                # Try to normalize date format and calculate warranty status
                for date_format in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        expiry_date = datetime.strptime(warranty_expiry, date_format)
                        normalized_warranty_expiry = expiry_date.strftime("%Y-%m-%d")
                        current_date = datetime.now()
                        warranty_status = (
                            "Active" if expiry_date > current_date else "Expired"
                        )
                        break
                    except ValueError:
                        continue

            # Format output to match mock data format exactly
            laptop_info = f"""
    Employee Name: {user_data.get("name", "N/A")}
    Employee ID: {user_data.get("sys_id", "N/A")}
    Employee Location: {location_value}
    Laptop Model: {model_value}
    Laptop Serial Number: {computer_data.get("serial_number", "N/A")}
    Laptop Purchase Date: {normalized_purchase_date}
    Laptop Age: {laptop_age}
    Laptop Warranty Expiry Date: {normalized_warranty_expiry}
    Laptop Warranty: {warranty_status}
    """

            return laptop_info

        except Exception as e:
            logger.error(
                "Error formatting laptop info",
                error=str(e),
                error_type=type(e).__name__,
            )
            return f"Error: Failed to format laptop information - {str(e)}"

    def get_open_laptop_requests_for_user(self, user_sys_id: str) -> Dict[str, Any]:
        """
        Fetches open laptop refresh requests for a specific user.

        Args:
            user_sys_id: The sys_id of the user to search for open requests.

        Returns:
            Dictionary containing the result of the operation with success, message, and requests data.
        """
        if not user_sys_id:
            return {"success": False, "message": "User sys_id parameter is required"}

        # Build query parameters to find open request items for the user
        # Look for request items where:
        # - who_is_this_request_for equals user_sys_id
        # - state is open (typically states 1, 2)
        # - cat_item points to the laptop refresh catalog item
        params = {
            "sysparm_query": f"who_is_this_request_for={user_sys_id}^stateIN1,2^cat_item={self.laptop_refresh_id}",
            "sysparm_fields": "number,variables.laptop_choices,state,request.number",
        }

        try:
            data = self._get("/api/now/table/sc_req_item", params)

            if not data:
                return {
                    "success": False,
                    "message": "Failed to connect to ServiceNow API",
                }

            if data and data.get("result"):
                requests = data["result"]
                return {
                    "success": True,
                    "message": f"Found {len(requests)} open laptop request(s) for user",
                    "requests": requests,
                }
            else:
                logger.info(
                    "No open laptop requests found for user", user_sys_id=user_sys_id
                )
                return {
                    "success": True,
                    "message": "No open laptop requests found for user",
                    "requests": [],
                }

        except Exception as e:
            logger.error(
                "Failed to get open laptop requests for user",
                user_sys_id=user_sys_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {
                "success": False,
                "message": f"Failed to get open laptop requests: {str(e)}",
            }
