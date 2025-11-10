"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets.
"""

import logging
import os
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from snow.data.data import (
    create_laptop_refresh_ticket,
    find_employee_by_authoritative_user_id,
    format_laptop_info,
)
from snow.servicenow.client import ServiceNowClient
from snow.servicenow.models import OpenServiceNowLaptopRefreshRequestParams
from starlette.responses import JSONResponse
from tracing_config.auto_tracing import run as auto_tracing_run
from tracing_config.auto_tracing import tracingIsActive

SERVICE_NAME = "snow-mcp-server"
logger = logging.getLogger(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)

MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get("MCP_TRANSPORT", "sse")  # type: ignore[assignment]
MCP_PORT = int(
    os.environ.get("SELF_SERVICE_AGENT_SNOW_SERVER_SERVICE_PORT_HTTP", "8001")
)
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
mcp = FastMCP(
    "Snow Server", host=MCP_HOST, stateless_http=(MCP_TRANSPORT == "streamable-http")
)


def _should_use_real_servicenow() -> bool:
    """Determine if real ServiceNow should be used based on environment configuration."""
    servicenow_url = os.getenv("SERVICENOW_INSTANCE_URL")
    use_real = os.getenv("USE_REAL_SERVICENOW", "false").lower() == "true"

    return bool(servicenow_url and use_real)


def _create_real_servicenow_ticket(
    authoritative_user_id: str, preferred_model: str, api_token: str | None = None
) -> str:
    """Create a real ServiceNow ticket using the API.

    Args:
        authoritative_user_id: Authoritative user ID from request headers
        preferred_model: ServiceNow laptop model code
        api_token: Optional API token from request header

    Returns:
        ServiceNow ticket creation result message
    """
    try:
        client = ServiceNowClient(api_token)

        # Look up user sys_id by email as currently only email is supported
        # authoritative user id
        logging.info(f"Looking up sys_id for email: {authoritative_user_id}")
        user_result = client.get_user_by_email(authoritative_user_id)
        if user_result.get("success") and user_result.get("user"):
            user_sys_id = user_result["user"].get("sys_id")
            if not user_sys_id:
                raise ValueError(
                    f"User found but sys_id is missing for email: {authoritative_user_id}"
                )
            logging.info(f"Found sys_id: {user_sys_id}")
        else:
            error_msg = user_result.get("message", "Unknown error")
            raise ValueError(
                f"Could not find user for email {authoritative_user_id}: {error_msg}"
            )

        params = OpenServiceNowLaptopRefreshRequestParams(
            who_is_this_request_for=user_sys_id,
            laptop_choices=preferred_model,
        )

        result = client.open_laptop_refresh_request(params)

        # Extract the required fields from the result
        if result.get("success") and result.get("data", {}).get("result"):
            logging.info(
                f"ServiceNow API request completed - authoritative_user_id: {authoritative_user_id}, "
                f"laptop: {preferred_model}, success: {result.get('success', False)}"
            )

            result_data = result["data"]["result"]
            request_number = result_data.get("request_number", "N/A")
            sys_id = result_data.get("sys_id", "N/A")

            return f"{request_number} opened for employee {authoritative_user_id}. System ID: {sys_id}"
        else:
            # Return error message if the request failed
            error_msg = result.get("message", "Unknown error occurred")
            return f"Failed to open laptop refresh request for employee {authoritative_user_id}: {error_msg}"

    except Exception as e:
        error_msg = f"Error opening ServiceNow laptop refresh request: {str(e)}"
        logging.error(error_msg)
        raise  # Re-raise to allow fallback handling


def _extract_authoritative_user_id(ctx: Context[Any, Any]) -> str | None:
    """Extract authoritative user ID from request context headers.

    Args:
        ctx: Request context containing headers

    Returns:
        Authoritative user ID if found, None otherwise
    """
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers
                user_id = headers.get("AUTHORITATIVE_USER_ID") or headers.get(
                    "authoritative_user_id"
                )
                return str(user_id) if user_id is not None else None
    except Exception as e:
        logging.debug(f"Error extracting headers from request context: {e}")

    return None


def _extract_servicenow_token(ctx: Context[Any, Any]) -> str | None:
    """Extract ServiceNow API token from request context headers.

    This implements pass-through authentication where the client (agent-service)
    reads the API key from its environment and passes it via the X-ServiceNow-Token header.

    Args:
        ctx: Request context containing headers

    Returns:
        ServiceNow API token if found, None otherwise
    """
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers
                # Check both uppercase and lowercase variants
                token = headers.get("SERVICE_NOW_TOKEN")
                return str(token) if token is not None else None
    except Exception as e:
        logging.debug(f"Error extracting ServiceNow token from request context: {e}")

    return None


def _get_real_servicenow_laptop_info(
    authoritative_user_id: str, api_token: str | None = None
) -> str:
    """Get laptop information from real ServiceNow API.

    Note: ServiceNow API currently only supports email-based lookups.
    If an employee ID is provided, this will likely fail.

    Args:
        authoritative_user_id: Authoritative user ID from request headers (email or employee ID)
        api_token: Optional API token from request header
    Returns:
        Formatted laptop information string including employee details and hardware specifications
    """
    try:
        client = ServiceNowClient(api_token)

        laptop_info = client.get_employee_laptop_info(authoritative_user_id)
        if laptop_info:
            return laptop_info
        else:
            return f"Error: Failed to retrieve laptop info for {authoritative_user_id} from ServiceNow"
    except Exception as e:
        error_msg = f"Error getting laptop info from ServiceNow: {str(e)}"
        logging.error(error_msg)
        raise  # Re-raise to allow fallback handling


def _get_mock_laptop_info(authoritative_user_id: str) -> str:
    """Get laptop information from mock data.

    Args:
        authoritative_user_id: Authoritative user ID from request headers (email address)

    Returns:
        Formatted laptop information string including employee details and hardware specifications
    """
    employee_data = find_employee_by_authoritative_user_id(authoritative_user_id)

    # filters out some fields and adds others
    return format_laptop_info(employee_data)


@mcp.custom_route("/health", methods=["GET"])  # type: ignore
async def health(request: Any) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def open_laptop_refresh_ticket(
    employee_name: str,
    business_justification: str,
    servicenow_laptop_code: str,
    ctx: Context[Any, Any],
) -> str:
    """Open a ServiceNow laptop refresh ticket for an employee.

    Args:
        employee_name: The full name of the employee
        business_justification: Business reason for the laptop refresh request
        servicenow_laptop_code: ServiceNow laptop choice code from the catalog item.
                               Examples: 'apple_mac_book_air_m_3', 'lenovo_think_pad_p_16_gen_2',
                               'lenovo_think_pad_t_14_s_gen_5_amd'
                               IMPORTANT: This must be the exact ServiceNow Code from the knowledge base,
                               NOT the human-readable model name.
    Returns:
        A formatted string containing the ticket details
    """
    if not employee_name:
        raise ValueError("Employee name cannot be empty")

    if not business_justification:
        raise ValueError("Business justification cannot be empty")

    if not servicenow_laptop_code:
        raise ValueError(
            "ServiceNow laptop code cannot be empty. Must be a valid ServiceNow laptop choice code like 'apple_mac_book_air_m_3'."
        )

    authoritative_user_id = _extract_authoritative_user_id(ctx)
    api_token = _extract_servicenow_token(ctx)

    if not authoritative_user_id:
        raise ValueError(
            "Authoritative user ID not found in request headers. Ensure AUTHORITATIVE_USER_ID header is set."
        )

    # Try real ServiceNow first if configured
    if _should_use_real_servicenow():
        if not api_token:
            raise ValueError(
                "ServiceNow API token is required for real ServiceNow integration. "
            )
        logging.info(
            f"Using real ServiceNow API - authoritative_user_id: {authoritative_user_id}, laptop_code: {servicenow_laptop_code}"
        )
        return _create_real_servicenow_ticket(
            authoritative_user_id, servicenow_laptop_code, api_token
        )

    # Use mock implementation
    logging.info(
        f"Using mock ServiceNow implementation - authoritative_user_id: {authoritative_user_id}, laptop_code: {servicenow_laptop_code}"
    )
    return create_laptop_refresh_ticket(
        authoritative_user_id=authoritative_user_id,
        employee_name=employee_name,
        business_justification=business_justification,
        preferred_model=servicenow_laptop_code,
    )


@mcp.tool()
def get_employee_laptop_info(
    ctx: Context[Any, Any],
    dummy_parameter: str = "",
) -> str:
    """Get laptop information for an employee using their authoritative user ID from request headers.

    This function retrieves and returns detailed information about an employee's laptop,
    including personal details, hardware specifications, purchase information, calculated
    age, and warranty status.

    Args:
        dummy_parameter: Optional parameter as validation fails unless there is at least one parameter

    Returns:
        A formatted multi-line string containing the following information:
        - Employee Name: Full name of the employee
        - Employee Location: Geographic region (EMEA, LATAM, APAC, etc.)
        - Laptop Model: Brand and model of the laptop
        - Laptop Serial Number: Unique serial number
        - Laptop Purchase Date: Date when laptop was purchased (YYYY-MM-DD format)
        - Laptop Age: Calculated age in years and months from purchase date to current date
        - Laptop Warranty Expiry Date: When the warranty expires (YYYY-MM-DD format)
        - Laptop Warranty: Current warranty status (Active/Expired)

    Raises:
        ValueError: If AUTHORITATIVE_USER_ID header is not present or employee is not found

    Examples:
        >>> # With AUTHORITATIVE_USER_ID header set to "alice.johnson@company.com"
        >>> get_employee_laptop_info(ctx)
        # Returns laptop info for alice.johnson@company.com
    """
    # Extract authoritative user ID from request headers - CENTRALIZED HANDLING
    authoritative_user_id = _extract_authoritative_user_id(ctx)
    api_token = _extract_servicenow_token(ctx)

    if not authoritative_user_id:
        raise ValueError(
            "Authoritative user ID not found in request headers. Ensure AUTHORITATIVE_USER_ID header is set."
        )

    # Try real ServiceNow first if configured, otherwise use mock
    if _should_use_real_servicenow():
        if not api_token:
            raise ValueError(
                "ServiceNow API token is required for real ServiceNow integration. "
            )
        logging.info(
            f"Using real ServiceNow API for laptop info - authoritative_user_id: {authoritative_user_id}"
        )
        return _get_real_servicenow_laptop_info(authoritative_user_id, api_token)

    # Use mock implementation
    logging.info(
        f"Using mock laptop info implementation - authoritative_user_id: {authoritative_user_id}"
    )

    result = _get_mock_laptop_info(authoritative_user_id)

    logging.info(
        f"returning laptop info for employee - authoritative_user_id: {authoritative_user_id}"
    )

    return result


if tracingIsActive():
    # TODO: trace the MCP requests
    pass


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


# Expose the ASGI app for uvicorn (for streamable-http transport)
app = mcp.streamable_http_app()


if __name__ == "__main__":
    main()
