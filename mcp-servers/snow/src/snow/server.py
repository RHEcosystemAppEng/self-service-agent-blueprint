"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets and ServiceNow API operations.
"""

import logging
import os
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from snow.data.data import create_laptop_refresh_ticket
from snow.servicenow.client import ServiceNowClient
from snow.servicenow.models import OpenServiceNowLaptopRefreshRequestParams
from starlette.responses import JSONResponse

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "sse")
MCP_PORT = int(
    os.environ.get("SELF_SERVICE_AGENT_SNOW_SERVER_SERVICE_PORT_HTTP", "8001")
)
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
mcp = FastMCP("Snow Server", host=MCP_HOST)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def open_laptop_refresh_ticket(
    employee_id: str,
    employee_name: str,
    business_justification: str,
    preferred_model: str = None,
) -> str:
    """Open a ServiceNow laptop refresh ticket for an employee.

    Args:
        employee_id: The unique identifier for the employee (e.g., '1001')
        employee_name: The full name of the employee
        business_justification: Business reason for the laptop refresh request
        preferred_model: Optional preferred laptop model (defaults to standard business laptop)

    Returns:
        A formatted string containing the ticket details
    """
    if not employee_id:
        raise ValueError("Employee ID cannot be empty")

    if not employee_name:
        raise ValueError("Employee name cannot be empty")

    if not business_justification:
        raise ValueError("Business justification cannot be empty")

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
        f"created service now ticket - employee_id: {employee_id}, ticket_number: {ticket_data['ticket_number']}"
    )
    return ticket_details


@mcp.tool()
def open_service_now_laptop_refresh_request(
    employee_service_now_id: str = "",
    preferred_model: str = "lenovo_think_pad_p_16_gen_2",
) -> str:
    """Open a ServiceNow laptop refresh request using the ServiceNow API.

    Args:
        employee_service_now_id: User ID for whom this request is being made (required)
        preferred_model: Laptop choice for the refresh request (default: lenovo_think_pad_p_16_gen_2)

    Returns:
        A formatted string containing the request number, employee ID, and system ID
    """
    if not employee_service_now_id:
        raise ValueError("employee_service_now_id parameter is required")

    try:
        client = ServiceNowClient()
        params = OpenServiceNowLaptopRefreshRequestParams(
            who_is_this_request_for=employee_service_now_id,
            laptop_choices=preferred_model,
        )

        result = client.open_laptop_refresh_request(params)

        # Extract the required fields from the result
        if result.get("success") and result.get("data", {}).get("result"):
            logging.info(
                f"ServiceNow API request completed - employee ID: {employee_service_now_id}, "
                f"laptop: {preferred_model}, success: {result.get('success', False)}"
            )

            result_data = result["data"]["result"]
            request_number = result_data.get("request_number", "N/A")
            sys_id = result_data.get("sys_id", "N/A")

            return f"{request_number} opened for employee {employee_service_now_id}. System ID: {sys_id}"
        else:
            # Return error message if the request failed
            error_msg = result.get("message", "Unknown error occurred")
            return f"Failed to open laptop refresh request for employee {employee_service_now_id}: {error_msg}"

    except Exception as e:
        error_msg = f"Error opening ServiceNow laptop refresh request: {str(e)}"
        logging.error(error_msg)
        return f"Failed to open laptop refresh request for employee {employee_service_now_id}: {error_msg}"


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
