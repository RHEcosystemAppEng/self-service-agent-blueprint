"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Literal

from mcp.server.fastmcp import Context, FastMCP
from shared_models import configure_logging
from snow.servicenow import headers
from snow.servicenow.client import ServiceNowClient
from snow.servicenow.models import OpenServiceNowLaptopRefreshRequestParams
from snow.tracing import trace_mcp_tool
from starlette.responses import JSONResponse
from tracing_config.auto_tracing import run as auto_tracing_run

SERVICE_NAME = "snow-mcp-server"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncGenerator[None, None]:
    """Initialize and validate ServiceNow configuration at startup."""
    # Startup: Validate and store required environment variables
    logger.info("Initializing ServiceNow configuration")

    laptop_refresh_id = os.getenv("SERVICENOW_LAPTOP_REFRESH_ID")
    if not laptop_refresh_id:
        logger.error(
            "SERVICENOW_LAPTOP_REFRESH_ID environment variable is not set. "
            "Please set it to the ServiceNow catalog item ID for laptop refresh requests."
        )
        raise ValueError(
            "SERVICENOW_LAPTOP_REFRESH_ID environment variable is required but not set. "
            "Please configure it in your deployment."
        )

    # Get laptop request limits with None if not set (no default limit)
    laptop_request_limits_env = os.getenv("SERVICENOW_LAPTOP_REQUEST_LIMITS")
    laptop_request_limits = (
        int(laptop_request_limits_env) if laptop_request_limits_env else None
    )

    # Get laptop avoid duplicates setting with default value of False
    laptop_avoid_duplicates_env = os.getenv(
        "SERVICENOW_LAPTOP_AVOID_DUPLICATES", "false"
    )
    laptop_avoid_duplicates = laptop_avoid_duplicates_env.lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

    # Store the laptop_refresh_id, limits, and avoid_duplicates setting on the app instance
    setattr(app, "laptop_refresh_id", laptop_refresh_id)
    setattr(app, "laptop_request_limits", laptop_request_limits)
    setattr(app, "laptop_avoid_duplicates", laptop_avoid_duplicates)
    logger.info(
        "ServiceNow configuration initialized",
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=laptop_avoid_duplicates,
    )

    try:
        yield
    finally:
        # Cleanup
        logger.info("Shutting down ServiceNow MCP server")


MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = os.environ.get("MCP_TRANSPORT", "sse")  # type: ignore[assignment]
MCP_PORT = int(
    os.environ.get("SELF_SERVICE_AGENT_SNOW_SERVER_SERVICE_PORT_HTTP", "8001")
)
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
mcp = FastMCP(
    "Snow Server",
    host=MCP_HOST,
    stateless_http=(MCP_TRANSPORT == "streamable-http"),
    lifespan=lifespan,
)


@mcp.custom_route("/health", methods=["GET"])  # type: ignore
async def health(request: Any) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
@trace_mcp_tool()
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
    try:
        if not employee_name:
            raise ValueError("Employee name cannot be empty")

        if not business_justification:
            raise ValueError("Business justification cannot be empty")

        if not servicenow_laptop_code:
            raise ValueError(
                "ServiceNow laptop code cannot be empty. Must be a valid ServiceNow laptop choice code like 'apple_mac_book_air_m_3'."
            )

        authoritative_user_id = headers.extract_authoritative_user_id(ctx)
        api_token = headers.extract_servicenow_token(ctx)

        if not authoritative_user_id:
            raise ValueError(
                "Authoritative user ID not found in request headers. Ensure AUTHORITATIVE_USER_ID header is set."
            )

        # Create ServiceNow ticket using the configured ServiceNow instance
        # (which could be real ServiceNow or mock server based on SERVICENOW_INSTANCE_URL)
        logger.info(
            "Creating ServiceNow ticket",
            tool="open_laptop_refresh_ticket",
            authoritative_user_id=authoritative_user_id,
            laptop_code=servicenow_laptop_code,
        )

        client = ServiceNowClient(
            api_token,
            getattr(mcp, "laptop_refresh_id"),
            getattr(mcp, "laptop_request_limits"),
            getattr(mcp, "laptop_avoid_duplicates"),
        )

        # Look up user sys_id by email as currently only email is supported
        # authoritative user id
        logger.info(
            "Looking up sys_id for email",
            tool="open_laptop_refresh_ticket",
            email=authoritative_user_id,
        )
        user_result = client.get_user_by_email(authoritative_user_id)
        if user_result.get("success") and user_result.get("user"):
            user_sys_id = user_result["user"].get("sys_id")
            if not user_sys_id:
                raise ValueError(
                    f"User found but sys_id is missing for email: {authoritative_user_id}"
                )
            logger.info(
                "Found sys_id",
                tool="open_laptop_refresh_ticket",
                user_sys_id=user_sys_id,
            )
        else:
            error_msg = user_result.get("message", "Unknown error")
            raise ValueError(
                f"Could not find user for email {authoritative_user_id}: {error_msg}"
            )

        params = OpenServiceNowLaptopRefreshRequestParams(
            who_is_this_request_for=user_sys_id,
            laptop_choices=servicenow_laptop_code,
        )

        result = client.open_laptop_refresh_request(params)

        # Extract the required fields from the result
        if result.get("success") and result.get("data", {}).get("result"):
            logger.info(
                "ServiceNow API request completed",
                tool="open_laptop_refresh_ticket",
                authoritative_user_id=authoritative_user_id,
                laptop=servicenow_laptop_code,
                success=result.get("success", False),
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
        logger.error(error_msg)
        return error_msg


@mcp.tool()
@trace_mcp_tool()
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
    try:
        # Extract authoritative user ID from request headers - CENTRALIZED HANDLING
        authoritative_user_id = headers.extract_authoritative_user_id(ctx)
        api_token = headers.extract_servicenow_token(ctx)

        if not authoritative_user_id:
            raise ValueError(
                "Authoritative user ID not found in request headers. Ensure AUTHORITATIVE_USER_ID header is set."
            )

        # Get laptop info from ServiceNow instance
        # (which could be real ServiceNow or mock server based on SERVICENOW_INSTANCE_URL)
        logger.info(
            "Getting laptop info from ServiceNow",
            tool="get_employee_laptop_info",
            authoritative_user_id=authoritative_user_id,
        )

        client = ServiceNowClient(
            api_token,
            getattr(mcp, "laptop_refresh_id"),
            getattr(mcp, "laptop_request_limits"),
            getattr(mcp, "laptop_avoid_duplicates"),
        )

        laptop_info = client.get_employee_laptop_info(authoritative_user_id)
        if laptop_info:
            result = laptop_info
        else:
            result = f"Error: Failed to retrieve laptop info for {authoritative_user_id} from ServiceNow"

        logger.info(
            "Returning laptop info for employee",
            tool="get_employee_laptop_info",
            authoritative_user_id=authoritative_user_id,
            result=result,  # TODO only for debugging
        )

        return result
    except Exception as e:
        error_msg = f"Error getting laptop info from ServiceNow: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


# Expose the ASGI app for uvicorn (for streamable-http transport)
app = mcp.streamable_http_app()


if __name__ == "__main__":
    main()
