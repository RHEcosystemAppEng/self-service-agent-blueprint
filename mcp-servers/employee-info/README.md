# Employee Info MCP Server

A FastMCP server that provides tools for retrieving employee laptop information. This server implements the Model Context Protocol (MCP) to expose employee laptop data through standardized tools.

## Features

- **Employee Laptop Information**: Retrieve detailed laptop specifications and assignment information for employees
- **Mock Data**: Uses sample data for demonstration purposes

## Tools

### `get_employee_laptop_info(employee_id: str)`

Retrieves comprehensive laptop information for a specific employee.

**Parameters:**
- `employee_id` (string): The unique identifier for the employee (e.g., 'emp001')

**Returns:**
- Employee details (name, department, email)
- Laptop specifications (brand, model, serial number, specs)
- Assignment and warranty information
- IT contact details

## Development Commands

Navigate to the `mcp-servers/employee-info/` directory for all development operations:

```bash
# Sync project dependencies
uv sync --all-packages

# Run unit tests
uv run pytest

# Code formatting and linting
uv run black .
uv run flake8 .

# Run the MCP server
uv run python -m employee_info.server
```

## Usage

### Running the Server

```bash
cd mcp-servers/employee-info/
uv run python -m employee_info.server
```

### Testing with FastMCP Client

```python
import asyncio
from fastmcp import Client

async def test_employee_info():
    client = Client("python -m employee_info.server")
    
    async with client:
        # Get specific employee laptop info
        laptop_info = await client.call_tool("get_employee_laptop_info", {
            "employee_id": "emp001"
        })
        print("Laptop Info:", laptop_info.data)

asyncio.run(test_employee_info())
```

## Sample Data

The server includes mock data for three employees:

| Employee ID | Name | Department | Device | Warranty Status |
|-------------|------|------------|--------|--------------|
| emp001 | Alice Johnson | Engineering | Dell Latitude 7420 | **Expired** |
| emp002 | John Doe | Marketing | MacBook Pro 14-inch | **Active** |
| emp003 | Maria Garcia | Finance | Lenovo ThinkPad X1 Carbon | **Active** |

## Container Operations

```bash
# Build container
cd mcp-servers/employee-info/
podman build -t employee-info-mcp .

# Run container
podman run --rm -p 8080:8080 employee-info-mcp
```

## Architecture

This MCP server follows the FastMCP framework patterns:

- **Tools**: Expose callable functions to MCP clients
- **Type Safety**: Full Python type hints and validation
- **Error Handling**: Proper exception handling with meaningful messages
- **Testing**: Comprehensive test coverage with pytest

## Project Structure

```
employee-info/
├── src/
│   └── employee_info/
│       ├── __init__.py
│       └── server.py          # Main MCP server implementation
├── tests/
│   └── test_employee_info.py  # Unit tests
├── pyproject.toml             # Project configuration
├── README.md                  # This file
├── uv.lock                    # Dependency lock file
└── Containerfile             # Container build instructions
```

## Development Standards

- Format all Python code with `black`
- Lint with `flake8`
- Use type hints and docstrings
- Follow PEP 8 guidelines
- Python 3.12+ required