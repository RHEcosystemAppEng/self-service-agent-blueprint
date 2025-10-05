"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets.
"""

import logging
import os

from mcp.server.fastmcp import Context, FastMCP
from snow.data.data import create_laptop_refresh_ticket, get_mock_laptop_info
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
        params = OpenServiceNowLaptopRefreshRequestParams(
            who_is_this_request_for=employee_id,
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


def _get_real_servicenow_laptop_info(employee_email: str) -> str:
    """Get laptop information from real ServiceNow API."""
    try:
        client = ServiceNowClient()

        laptop_info = client.get_employee_laptop_info(employee_email)
        if laptop_info:
            return laptop_info
        else:
            return f"Error: Failed to retrieve laptop info for {employee_email} from ServiceNow"
    except Exception as e:
        error_msg = f"Error getting laptop info from ServiceNow: {str(e)}"
        logging.error(error_msg)
        raise  # Re-raise to allow fallback handling


def _get_mock_laptop_info(employee_email: str) -> str:
    """Get laptop information from mock data."""
    return get_mock_laptop_info(employee_email)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def open_laptop_refresh_ticket(
    employee_id: str,
    employee_name: str,
    business_justification: str,
    ctx: Context,
    preferred_model: str = None,
) -> str:
    """Open a ServiceNow laptop refresh ticket for an employee.

    Args:
        employee_id: The unique identifier for the employee (e.g., '1001')
        employee_name: The full name of the employee
        business_justification: Business reason for the laptop refresh request
        preferred_model: Preferred laptop model

    Returns:
        A formatted string containing the ticket details
    """
    if not employee_id:
        raise ValueError("Employee ID cannot be empty")

    if not employee_name:
        raise ValueError("Employee name cannot be empty")

    if not business_justification:
        raise ValueError("Business justification cannot be empty")

    if not preferred_model:
        raise ValueError("Preferred model cannot be empty")

    # Extract authoritative user ID from request headers via Context
    authoritative_user_id = None
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers

                authoritative_user_id = headers.get(
                    "AUTHORITATIVE_USER_ID"
                ) or headers.get("authoritative_user_id")
    except Exception as e:
        logging.debug(f"Error extracting headers from request context: {e}")
        authoritative_user_id = None

    # Try real ServiceNow first if configured, otherwise use mock
    if _should_use_real_servicenow():
        try:
            logging.info(
                f"Using real ServiceNow API - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_id}"
            )
            return _create_real_servicenow_ticket(employee_id, preferred_model)
        except Exception as e:
            logging.warning(f"ServiceNow API failed, falling back to mock: {e}")
            # Fall through to mock implementation

    # Use mock implementation
    logging.info(
        f"Using mock ServiceNow implementation - authoritative_user_id: {authoritative_user_id}, employee_id: {employee_id}"
    )
    return _create_mock_ticket(
        employee_id,
        employee_name,
        business_justification,
        preferred_model,
        authoritative_user_id,
    )


@mcp.tool()
def get_employee_laptop_info(
    employee_email: str,
    ctx: Context,
) -> str:
    """Get laptop information for an employee by their email address.

    Args:
        employee_email: The email address of the employee

    Returns:
        A formatted string containing the employee's laptop information
    """
    if not employee_email:
        raise ValueError("Employee email cannot be empty")

    # Extract authoritative user ID from request headers via Context
    authoritative_user_id = None
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers

                authoritative_user_id = headers.get(
                    "AUTHORITATIVE_USER_ID"
                ) or headers.get("authoritative_user_id")
    except Exception as e:
        logging.debug(f"Error extracting headers from request context: {e}")
        authoritative_user_id = None

    # Try real ServiceNow first if configured, otherwise use mock
    if _should_use_real_servicenow():
        try:
            logging.info(
                f"Using real ServiceNow API for laptop info - authoritative_user_id: {authoritative_user_id}, employee_email: {employee_email}"
            )
            return _get_real_servicenow_laptop_info(employee_email)
        except Exception as e:
            logging.warning(
                f"ServiceNow API failed for laptop info, falling back to mock: {e}"
            )
            # Fall through to mock implementation

    # Use mock implementation
    logging.info(
        f"Using mock laptop info implementation - authoritative_user_id: {authoritative_user_id}, employee_email: {employee_email}"
    )
    return _get_mock_laptop_info(employee_email)


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
