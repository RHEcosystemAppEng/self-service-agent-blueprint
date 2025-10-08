"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets.
"""

import logging
import os

from mcp.server.fastmcp import Context, FastMCP
from snow.data.data import (
    create_laptop_refresh_ticket,
    find_employee_by_id_or_email,
    format_laptop_info,
)
from snow.servicenow.client import ServiceNowClient
from snow.servicenow.models import OpenServiceNowLaptopRefreshRequestParams
from starlette.responses import JSONResponse

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "sse")
MCP_PORT = int(
    os.environ.get("SELF_SERVICE_AGENT_SNOW_SERVER_SERVICE_PORT_HTTP", "8001")
)
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
mcp = FastMCP("Snow Server", host=MCP_HOST)


def _should_use_real_servicenow() -> bool:
    """Determine if real ServiceNow should be used based on environment configuration."""
    servicenow_url = os.getenv("SERVICENOW_INSTANCE_URL")
    use_real = os.getenv("USE_REAL_SERVICENOW", "false").lower() == "true"

    return bool(servicenow_url and use_real)


def _create_real_servicenow_ticket(employee_id: str, preferred_model: str) -> str:
    """Create a real ServiceNow ticket using the API."""
    try:
        client = ServiceNowClient()

        # Look up user sys_id if employee_id looks like an email
        user_sys_id = employee_id
        if "@" in employee_id:
            logging.info(f"Looking up sys_id for email: {employee_id}")
            user_result = client.get_user_by_email(employee_id)
            if user_result.get("success") and user_result.get("user"):
                user_sys_id = user_result["user"].get("sys_id", employee_id)
                logging.info(f"Found sys_id: {user_sys_id}")
            else:
                logging.warning(
                    f"Could not find user for email {employee_id}, using as-is"
                )

        params = OpenServiceNowLaptopRefreshRequestParams(
            who_is_this_request_for=user_sys_id,
            laptop_choices=preferred_model,
        )

        result = client.open_laptop_refresh_request(params)

        # Extract the required fields from the result
        if result.get("success") and result.get("data", {}).get("result"):
            logging.info(
                f"ServiceNow API request completed - employee ID: {employee_id}, "
                f"laptop: {preferred_model}, success: {result.get('success', False)}"
            )

            result_data = result["data"]["result"]
            request_number = result_data.get("request_number", "N/A")
            sys_id = result_data.get("sys_id", "N/A")

            return f"{request_number} opened for employee {employee_id}. System ID: {sys_id}"
        else:
            # Return error message if the request failed
            error_msg = result.get("message", "Unknown error occurred")
            return f"Failed to open laptop refresh request for employee {employee_id}: {error_msg}"

    except Exception as e:
        error_msg = f"Error opening ServiceNow laptop refresh request: {str(e)}"
        logging.error(error_msg)
        raise  # Re-raise to allow fallback handling


def _create_mock_ticket(
    employee_id: str,
    employee_name: str,
    business_justification: str,
    preferred_model: str,
    authoritative_user_id: str,
) -> str:
    """Create a mock ticket using the existing mock implementation."""
    ticket_data = create_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
        preferred_model=preferred_model,
    )

    ticket_details = f"""
    ServiceNow Ticket Created Successfully!

    Ticket Number: {ticket_data['ticket_number']}
    Employee: {ticket_data['employee_name']} (ID: {ticket_data['employee_id']})
    Request Type: {ticket_data['request_type']}
    Status: {ticket_data['status']}
    Priority: {ticket_data['priority']}
    Preferred Model: {ticket_data['preferred_model']}
    Business Justification: {ticket_data['business_justification']}
    Created Date: {ticket_data['created_date']}
    Expected Completion: {ticket_data['expected_completion']}
    Assigned Group: {ticket_data['assigned_group']}

    Your laptop refresh request has been submitted and will be processed by the IT Hardware Team.
    You will receive updates via email as the ticket progresses.
    """

    logging.info(
        f"created service now ticket - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_id}, ticket_number: {ticket_data['ticket_number']}"
    )
    return ticket_details


def _extract_authoritative_user_id(ctx: Context) -> str:
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
                return headers.get("AUTHORITATIVE_USER_ID") or headers.get(
                    "authoritative_user_id"
                )
    except Exception as e:
        logging.debug(f"Error extracting headers from request context: {e}")

    return None


def _get_real_servicenow_laptop_info(
    employee_identifier: str, include_employee_id: bool = True
) -> str:
    """Get laptop information from real ServiceNow API.

    Note: ServiceNow API currently only supports email-based lookups.
    If an employee ID is provided, this will likely fail.

    Args:
        employee_identifier: Employee email address or ID (used for lookup)
        include_employee_id: Whether to include Employee ID in output

    Returns:
        Formatted laptop information string
    """
    try:
        client = ServiceNowClient()

        laptop_info = client.get_employee_laptop_info(employee_identifier)
        if laptop_info:
            # Remove Employee ID line from response if not needed
            if not include_employee_id and "Employee ID:" in laptop_info:
                lines = laptop_info.split("\n")
                filtered_lines = [
                    line
                    for line in lines
                    if not line.strip().startswith("Employee ID:")
                ]
                laptop_info = "\n".join(filtered_lines)
            return laptop_info
        else:
            return f"Error: Failed to retrieve laptop info for {employee_identifier} from ServiceNow"
    except Exception as e:
        error_msg = f"Error getting laptop info from ServiceNow: {str(e)}"
        logging.error(error_msg)
        raise  # Re-raise to allow fallback handling


def _get_mock_laptop_info(
    employee_identifier: str, include_employee_id: bool = True
) -> str:
    """Get laptop information from mock data.

    Supports lookup by both employee ID (e.g., '1001') and email address
    (e.g., 'alice.johnson@company.com').

    Args:
        employee_identifier: Employee ID or email address (used for lookup)
        include_employee_id: Whether to include Employee ID in output

    Returns:
        Formatted laptop information string
    """
    # Supports both employee ID and email lookups (O(1) performance)
    employee_data = find_employee_by_id_or_email(employee_identifier)

    # Format the output
    return format_laptop_info(employee_data, include_employee_id=include_employee_id)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def open_laptop_refresh_ticket(
    employee_id: str,
    employee_name: str,
    business_justification: str,
    servicenow_laptop_code: str,
    ctx: Context,
) -> str:
    """Open a ServiceNow laptop refresh ticket for an employee.

    Args:
        employee_id: The unique identifier for the employee (e.g., '1001')
        employee_name: The full name of the employee
        business_justification: Business reason for the laptop refresh request
        servicenow_laptop_code: ServiceNow laptop choice code from the catalog item.
                               Examples: 'apple_mac_book_air_m_3', 'lenovo_think_pad_p_16_gen_2',
                               'lenovo_think_pad_t_14_s_gen_5_amd'
                               IMPORTANT: This must be the exact ServiceNow Code from the knowledge base,
                               NOT the human-readable model name.
        ctx: Request context

    Returns:
        A formatted string containing the ticket details
    """
    if not employee_id:
        raise ValueError("Employee ID cannot be empty")

    if not employee_name:
        raise ValueError("Employee name cannot be empty")

    if not business_justification:
        raise ValueError("Business justification cannot be empty")

    if not servicenow_laptop_code:
        raise ValueError(
            "ServiceNow laptop code cannot be empty. Must be a valid ServiceNow laptop choice code like 'apple_mac_book_air_m_3'."
        )

    # Extract authoritative user ID from request headers - CENTRALIZED HANDLING
    authoritative_user_id = _extract_authoritative_user_id(ctx)

    # Use authoritative_user_id if available, otherwise fall back to employee_id
    user_identifier = authoritative_user_id if authoritative_user_id else employee_id

    # Try real ServiceNow first if configured, otherwise use mock
    if _should_use_real_servicenow():
        try:
            logging.info(
                f"Using real ServiceNow API - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_id}, using: {user_identifier}, laptop_code: {servicenow_laptop_code}"
            )
            return _create_real_servicenow_ticket(
                user_identifier, servicenow_laptop_code
            )
        except Exception as e:
            logging.warning(f"ServiceNow API failed, falling back to mock: {e}")
            # Fall through to mock implementation

    # Use mock implementation
    logging.info(
        f"Using mock ServiceNow implementation - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_id}, using: {user_identifier}, laptop_code: {servicenow_laptop_code}"
    )
    return _create_mock_ticket(
        user_identifier,
        employee_name,
        business_justification,
        servicenow_laptop_code,
        authoritative_user_id,
    )


@mcp.tool()
def get_employee_laptop_info(
    employee_identifier: str,
    ctx: Context,
) -> str:
    """Get laptop information for an employee by their ID or email address.

    This function retrieves and returns detailed information about an employee's laptop,
    including personal details, hardware specifications, purchase information, calculated
    age, and warranty status.

    Lookup Support:
    - Mock data: Supports BOTH employee ID and email address lookups
    - Real ServiceNow API: Only supports email address lookups (ServiceNow API limitation)

    If an AUTHORITATIVE_USER_ID header is present, it takes precedence over the provided
    employee_identifier parameter, and the employee ID will be excluded from the output.

    Args:
        employee_identifier: The employee identifier - either employee ID (e.g., '1001')
                           or email address (e.g., 'alice.johnson@company.com')
                           Note: Employee ID only works with mock data, not real ServiceNow API

    Returns:
        A formatted multi-line string containing the following information:
        - Employee Name: Full name of the employee
        - Employee ID: The employee's unique identifier (excluded when using AUTHORITATIVE_USER_ID)
        - Employee Location: Geographic region (EMEA, LATAM, APAC, etc.)
        - Laptop Model: Brand and model of the laptop
        - Laptop Serial Number: Unique serial number
        - Laptop Purchase Date: Date when laptop was purchased (YYYY-MM-DD format)
        - Laptop Age: Calculated age in years and months from purchase date to current date
        - Laptop Warranty Expiry Date: When the warranty expires (YYYY-MM-DD format)
        - Laptop Warranty: Current warranty status (Active/Expired)

    Raises:
        ValueError: If employee_identifier is empty or not found in the database

    Examples:
        >>> get_employee_laptop_info("1001", ctx)
        # Returns laptop info for employee ID 1001

        >>> get_employee_laptop_info("alice.johnson@company.com", ctx)
        # Returns the same information as above
    """
    if not employee_identifier:
        raise ValueError("Employee identifier cannot be empty")

    # Extract authoritative user ID from request headers - CENTRALIZED HANDLING
    authoritative_user_id = _extract_authoritative_user_id(ctx)

    # Determine lookup identifier and whether to include employee ID in output
    # If authoritative user is set, it takes precedence and employee ID is excluded
    lookup_identifier = (
        authoritative_user_id if authoritative_user_id else employee_identifier
    )
    include_employee_id = authoritative_user_id is None

    # Try real ServiceNow first if configured, otherwise use mock
    if _should_use_real_servicenow():
        try:
            logging.info(
                f"Using real ServiceNow API for laptop info - authoritative_user_id: {authoritative_user_id}, employee_identifier: {employee_identifier}, lookup_used: {lookup_identifier}"
            )
            return _get_real_servicenow_laptop_info(
                lookup_identifier, include_employee_id
            )
        except Exception as e:
            logging.warning(
                f"ServiceNow API failed for laptop info, falling back to mock: {e}"
            )
            # Fall through to mock implementation

    # Use mock implementation
    logging.info(
        f"Using mock laptop info implementation - authoritative_user_id: {authoritative_user_id}, employee_identifier: {employee_identifier}, lookup_used: {lookup_identifier}"
    )

    # Get employee data to log the actual employee_id being looked up
    employee_data = find_employee_by_id_or_email(lookup_identifier)
    result = _get_mock_laptop_info(lookup_identifier, include_employee_id)

    logging.info(
        f"returning laptop info for employee - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_data.get('employee_id')}, lookup_used: {lookup_identifier}"
    )

    return result


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
