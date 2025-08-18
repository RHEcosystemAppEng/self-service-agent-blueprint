"""Snow Server MCP Server.

A FastMCP server that provides tools for creating
ServiceNow laptop refresh tickets.
"""

import os
from mcp.server.fastmcp import FastMCP

from snow_server.data.data import create_laptop_refresh_ticket
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

    return ticket_details


def main() -> None:
    """Run the Snow Server MCP server."""
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
