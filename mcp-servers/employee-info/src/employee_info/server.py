"""Employee Info MCP Server.

A FastMCP server that provides tools for retrieving
employee laptop information.
"""

import os
from typing import Dict, Any
from fastmcp import FastMCP
from employee_info.data import MOCK_EMPLOYEE_DATA
from starlette.responses import JSONResponse

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "http")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
mcp = FastMCP("Employee Info Server")


def _get_employee_laptop_info(employee_id: str) -> Dict[str, Any]:
    if not employee_id:
        raise ValueError("Employee ID cannot be empty")

    employee_data = MOCK_EMPLOYEE_DATA.get(employee_id)

    if not employee_data:
        available_ids = list(MOCK_EMPLOYEE_DATA.keys())
        raise ValueError(
            f"Employee ID '{employee_id}' not found. "
            f"Available IDs: {', '.join(available_ids)}"
        )

    return employee_data


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "OK"})


@mcp.tool
def get_employee_laptop_info(employee_id: str) -> Dict[str, Any]:
    """Get laptop information for a specific employee.

    Args:
        employee_id: The unique identifier for the employee (e.g., '1001')

    Returns:
        Dictionary containing employee and laptop information including:
        - Employee details (name, department, email)
        - Laptop specifications (brand, model, serial number)
        - Assignment and warranty information
        - IT contact details

    Raises:
        ValueError: If employee_id is not found in the system
    """
    return _get_employee_laptop_info(employee_id)


def main() -> None:
    """Run the Employee Info MCP server."""
    if MCP_TRANSPORT == "http":
        mcp.run(transport=MCP_TRANSPORT, host="0.0.0.0", port=MCP_PORT)
    else:
        mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
