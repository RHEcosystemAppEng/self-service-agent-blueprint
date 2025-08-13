# Employee Info MCP Server

A FastMCP server that provides tools for retrieving employee laptop information. This server implements the Model Context Protocol (MCP) to expose employee laptop data through standardized tools.

## Features

- **Employee Laptop Information**: Retrieve detailed laptop specifications and assignment information for employees
- **Mock Data**: Uses sample data for demonstration purposes

## Tools

### `get_employee_laptop_info(employee_id: str)`

Retrieves comprehensive laptop information for a specific employee.

**Parameters:**
- `employee_id` (string): The unique identifier for the employee (e.g., '1001')

**Returns:**
- Employee details (name, department, email, location)
- Laptop specifications (brand, model, serial number, specs)
- Purchase and warranty information
- IT contact details
- Top-level laptop fields (laptop_model, laptop_serial_number)

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

## Sample Data

The server includes mock data for ten employees:

| Employee ID | Name | Department | Device | Warranty Status |
|-------------|------|------------|--------|--------------|
| 1001        | Alice Johnson | Engineering | Dell Latitude 7420 | Expired |
| 1002        | John Doe | Marketing | MacBook Pro 14-inch | Active |
| 1003        | Maria Garcia | Finance | Lenovo ThinkPad X1 Carbon | Active |
| ...         | ... | ... | ... | ... |
| 1010        | Ahmed Hassan | Quality Assurance | Inspiron 15 5000 | Expired |

## Container Operations

```bash
# Build container
cd mcp-servers/employee-info/
podman build -t employee-info-mcp .

# Run container
podman run --rm -i -p 8080:8080 \
  -e FASTMCP_HOST=0.0.0.0 \
  -e FASTMCP_PORT=8080 \
  employee-info-mcp
```

## Testing with MCP-Server with Claude Code + Podman

```base
# Add the local empoyee-info-mcp server to claude code 
claude mcp add --transport http employee-info-mcp http://localhost:8080/mcp

# Check the server has connected (pod should be running before)
claude mcp list
# Checking MCP server health...
# employee-info-mcp: http://localhost:8080/mcp (HTTP) - ✓ Connected

# Get into claude and test the tool
>  Has the warranty for employee with id 1001 expired?
# Should ask permission to use tool & return that the warranty has indeed expired
>  Has the warranty for employee with id 1002 expired?
# Should ask permission to use tool & return that the warranty has not expired yet
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
