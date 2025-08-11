"""Employee Info MCP Server.

A FastMCP server that provides tools for retrieving
employee laptop information.
"""

from typing import Dict, Any
from fastmcp import FastMCP
from employee_info.data import MOCK_EMPLOYEE_DATA


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


@mcp.tool
def get_employee_laptop_info(employee_id: str) -> Dict[str, Any]:
    """Get laptop information for a specific employee.

    Args:
        employee_id: The unique identifier for the employee (e.g., 'emp001')

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
    mcp.run()


if __name__ == "__main__":
    main()
