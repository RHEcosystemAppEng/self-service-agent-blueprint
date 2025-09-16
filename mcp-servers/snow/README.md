# Snow Server MCP Server

A FastMCP server that provides tools for creating ServiceNow laptop refresh tickets. This server implements the Model Context Protocol (MCP) to expose ServiceNow ticket creation functionality through standardized tools.

## Features

- **Laptop Refresh Tickets**: Create ServiceNow tickets for laptop refresh requests
- **Mock Data**: Uses simulated ServiceNow integration for demonstration purposes
- **Business Justification**: Requires business justification for all ticket requests

## Tools

### `open_laptop_refresh_ticket(employee_id: str, employee_name: str, business_justification: str, preferred_model: str = None)`

Creates a ServiceNow laptop refresh ticket for an employee.

**Parameters:**
- `employee_id` (string): The unique identifier for the employee (e.g., '1001')
- `employee_name` (string): The full name of the employee
- `business_justification` (string): Business reason for the laptop refresh request
- `preferred_model` (string, optional): Preferred laptop model (defaults to "Standard Business Laptop")

**Returns:**
- Ticket number and details
- Status and priority information
- Expected completion timeline
- Assigned group information

## Development Commands

Navigate to the `mcp-servers/snow/` directory for all development operations:

```bash
# Sync project dependencies
uv sync --all-packages

# Run unit tests
uv run pytest

# Code formatting and linting
uv run black .
uv run flake8 .

# Run the MCP server
uv run python -m snow.server
```

## Usage

### Running the Server

```bash
cd mcp-servers/snow/
uv run python -m snow.server
```

## Sample Usage

```python
# Create a laptop refresh ticket
ticket_details = open_laptop_refresh_ticket(
    employee_id="1001",
    employee_name="Alice Johnson",
    business_justification="Current laptop is 5 years old and experiencing frequent hardware failures",
    preferred_model="MacBook Pro 14-inch"
)
```

## Container Operations

```bash
# Build container
cd mcp-servers/snow/
podman build -t snow-mcp .

# Run container
podman run --rm -i -p 8000:800 snow-mcp
```

## Testing with MCP-Server with Claude Code + Podman

```bash
# Add the local snow-mcp server to claude code 
claude mcp add --transport http snow-mcp http://localhost:8000/mcp

# Check the server has connected (pod should be running before)
claude mcp list
# Checking MCP server health...
# snow-mcp: http://localhost:8000/mcp (HTTP) - ✓ Connected

# Get into claude and test the tool
>  I need to open a laptop refresh ticket for employee 1001, Alice Johnson. The current laptop is outdated and affecting productivity.
# Should ask permission to use tool & return ticket details with INC number
```

## Architecture

This MCP server follows the FastMCP framework patterns:

- **Tools**: Expose callable functions to MCP clients
- **Type Safety**: Full Python type hints and validation
- **Error Handling**: Proper exception handling with meaningful messages
- **Testing**: Comprehensive test coverage with pytest
- **Mock Integration**: Simulates ServiceNow API for demonstration

## Project Structure

```
snow/
├── src/
│   └── snow/
│       ├── __init__.py
│       ├── server.py           # Main MCP server implementation
│       └── data/
│           ├── __init__.py
│           └── data.py         # Mock ServiceNow data and ticket creation
├── tests/
│   └── test_snow.py     # Unit tests
├── pyproject.toml              # Project configuration
├── README.md                   # This file
├── uv.lock                     # Dependency lock file (generated)
└── Containerfile              # Container build instructions
```

## Environment Variables

- `MCP_TRANSPORT`: Transport protocol (default: "sse")
- `SELF_SERVICE_AGENT_SNOW_SERVER_SERVICE_PORT_HTTP`: HTTP port (default: 8001)
- `MCP_HOST`: Host address (default: "0.0.0.0")

## Error Handling

The server validates all required parameters and returns meaningful error messages:

- Empty employee ID, name, or business justification will raise `ValueError`
- All successful ticket creations return formatted ticket details
- Health check endpoint available at `/health`

## Attribution

The ServiceNow integration code in `src/snow/servicenow/` is based on the work from the [servicenow-mcp](https://github.com/echelon-ai-labs/servicenow-mcp) project by Echelon AI Labs. We acknowledge and appreciate their contribution to the ServiceNow MCP implementation.