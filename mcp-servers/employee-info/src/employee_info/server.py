"""Employee Info MCP Server.

A FastMCP server that provides tools for retrieving
employee laptop information.
"""

import os
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

from employee_info.data import MOCK_EMPLOYEE_DATA
from starlette.responses import JSONResponse

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "sse")
MCP_PORT = int(os.environ.get("SELF_SERVICE_AGENT_EMPLOYEE_INFO_SERVICE_PORT_HTTP", "8000"))
mcp = FastMCP("Employee Info Server", host="0.0.0.0")


def _get_employee_laptop_info(employee_id: str) -> str:
    if not employee_id:
        raise ValueError("Employee ID cannot be empty")

    employee_data = MOCK_EMPLOYEE_DATA.get(employee_id)

    if not employee_data:
        available_ids = list(MOCK_EMPLOYEE_DATA.keys())
        raise ValueError(
            f"Employee ID '{employee_id}' not found. "
            f"Available IDs: {', '.join(available_ids)}"
        )

    laptop_info = f"""
    Employee Laptop Information-
    Model: {employee_data.get("laptop_model")}
    Purchase Date: {employee_data.get("laptop", {}).get("purchase_date")}
    Warranty Expiry Date: {employee_data.get("laptop", {}).get("warranty_expiry")}
    Warranty Status: {employee_data.get("laptop", {}).get("warranty_status")}
    """
    return laptop_info


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool()
def get_employee_laptop_info(employee_id: str) -> str:
    """Return laptop details for a given employee ID: model, purchase date, warranty expiry date, and warranty status.

    Args:
        employee_id: The unique identifier for the employee (e.g., '1001')
    """
    return _get_employee_laptop_info(employee_id)


def main() -> None:
    """Run the Employee Info MCP server."""
    if MCP_TRANSPORT == "sse":
        #mcp.run(transport=MCP_TRANSPORT, host="0.0.0.0", port=MCP_PORT)
        mcp.run(transport=MCP_TRANSPORT)
    else:
        mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
