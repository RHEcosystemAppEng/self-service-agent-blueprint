# Snow Server MCP Server

A FastMCP server that provides tools for creating ServiceNow laptop refresh tickets. This server implements the Model Context Protocol (MCP) to expose ServiceNow ticket creation functionality through standardized tools.

## Features

- **Laptop Refresh Tickets**: Create ServiceNow tickets for laptop refresh requests
- **Mock Data**: Uses simulated ServiceNow integration for demonstration purposes
- **Business Justification**: Requires business justification for all ticket requests

## Tools

### `open_laptop_refresh_ticket(employee_id: str, employee_name: str, business_justification: str, preferred_model: str)`

Creates a ServiceNow laptop refresh ticket for an employee.

**Parameters:**
- `employee_id` (string): The unique identifier for the employee (e.g., '1001')
- `employee_name` (string): The full name of the employee
- `business_justification` (string): Business reason for the laptop refresh request
- `preferred_model` (string): Preferred laptop model (required)

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
- `SERVICENOW_INSTANCE_URL`: ServiceNow instance URL (e.g., "https://dev295439.service-now.com/")
- `SERVICENOW_AUTH_TYPE`: Authentication type: "basic", "oauth", or "api_key" (default: "basic")
- `USE_REAL_SERVICENOW`: if set to "true" will attempt to call the APIs of `SERVICENOW_INSTANCE_URL` (default: false)

### Basic Authentication
- `SERVICENOW_USERNAME`: ServiceNow username for authentication
- `SERVICENOW_PASSWORD`: ServiceNow password (sensitive - store as secret)

### OAuth Authentication
- `SERVICENOW_CLIENT_ID`: OAuth client ID
- `SERVICENOW_CLIENT_SECRET`: OAuth client secret
- `SERVICENOW_USERNAME`: ServiceNow username
- `SERVICENOW_PASSWORD`: ServiceNow password
- `SERVICENOW_TOKEN_URL`: OAuth token URL (optional)

### API Key Authentication
- `SERVICENOW_AUTH_TYPE=api_key`
- `SERVICENOW_API_KEY`: Your API key value
- `SERVICENOW_API_KEY_HEADER`: Custom header name (default: "x-sn-apikey")

## Creating ServiceNow API Keys

To use API key authentication with ServiceNow (recommended method), follow these steps:

### Prerequisites
1. Ensure the **API Key and HMAC Authentication** plugin (com.glide.tokenbased_auth) is activated
2. Navigate to **All > Admin Center > Application Manager** to verify activation

### Step 0: Create Service Account User

Before creating the API key, you need a service account user that will be associated with the API key. This user defines the permissions and data access for the API key.

1. Navigate to **All > User Administration > Users**
2. Click **New**
3. Fill in the form:
   - **User ID**: `svc_self_service_agent_mcp`
   - **First name**: `Service Now MCP Agent Prod`
4. Click **Submit**
5. After the user is created, assign the required roles:
   - In the user record, navigate to the **Roles** tab
   - Click **Edit** button in the related lists
   - Click **+** to add roles
   - Search for and add the following roles:
     - `cmdb_read` - Allows reading configuration management database (CMDB) data
   - Click **Save**



### Step 1: Create API KEY Authentication Profile

1. Navigate to **All > System Web Services > API Access Policies > Inbound Authentication Profile**
2. Click **New**
3. Click **Create API Key authentication profiles**
4. Fill in the form:
   - **Name**: `API Key`
   - **Auth Parameter**: Auth Header
     - From the dropdown, select: `x-sn-apikey`
     - This is the header name used by default and matches the MCP server configuration
5. Click **Submit**


### Step 1b: Create Basic Authentication Profile

To support both API key and basic authentication methods, create a Basic Authentication profile:

1. Navigate to **All > System Web Services > API Access Policies > Inbound Authentication Profile**
2. Click **New**
3. Click **Create Basic authentication profiles**
4. Fill in the form:
   - **Name**: `Basic Auth`
   - **Type**: `Basic Auth`
5. Click **Submit**

> **Tip**: The complete list of Auth Parameters is available at **All > System Web Services > API Access Policies > REST API Auth Parameter**

### Step 2: Create REST API Key

This generates the actual API key token that will be used for authentication. The API key is tied to the service account user you created in Step 0.

1. Navigate to **All > System Web Services > API Access Policies > REST API Key**
2. Click **New**
3. Fill in the form:
   - **Name**: `MCP Agent API Key - Production`
   - **User**: Search for and select `svc_self_service_agent_mcp` (the service account created in Step 0)
     - **Important**: This user's roles (cmdb_read) determine what data the API key can access
4. Use the form menu and choose **Save**
5. After saving, the system auto-generates a token in the **Token** field
6. Click the **lock icon** 🔒 to reveal and copy the token
7. **Save the token immediately** in a secure location (password manager, secret store, etc.)

> **Tip**: Use a non-user service account for APIs to avoid issues if employees leave

### Step 3: Create API Access Policy

This policy controls which REST APIs your API key can access and how it can interact with them. You'll create separate policies for each API endpoint your MCP agent needs.

1. Navigate to **All > System Web Services > API Access Policies > REST API Access Policies**
2. Click **New**
3. Fill in the form fields (see examples below)
4. Configure API access:
   - Select the REST API you want to use
   - Specify the REST API path
   - Add any table restrictions if needed
   - Configure method, resource, and version restrictions
5. Add the Authentication Profiles from Step 1 to the **Authentication** section
6. Click **Submit**

> **Note**: Create separate policies for different APIs. For example, one for Service Catalog (ticket creation) and another for Table API (data queries).

#### Configuration 1: Service Catalog API

For creating and managing ServiceNow tickets via the Service Catalog:

- **Name**: `Service Now - API Key Catalog`
- **REST API**: Service Catalog API
- **REST API Path**: `sn_sc/servicecatalog`
- **Methods**: Apply to all methods
- **Resources**: Apply to all resources
- **Versions**: Apply to all versions
- **Authentication profile**: Add both authentication profiles:
  - Select your "API Key" and "Basic Auth" Authentication Profiles
- Set to active

#### Configuration 2: Table API for Laptop Queries

For querying ServiceNow tables to retrieve laptop information:

- **Name**: `Service Now - API Key Tables`
- **REST API**: Table API
- **REST API Path**: `now/table`
- **Methods**: Apply to all methods
- **Resources**: Apply to all resources
- **Versions**: Apply to all versions
- **Tables**: Apply to all tables
- **Authentication profile**: Add both authentication profiles:
  - Select your "API Key" and "Basic Auth" Authentication Profiles
- Set to active

### Step 4: Test Your API Key

Verify that your API key works correctly using curl or any REST client:

```bash
# Test API key authentication
curl -H "x-sn-apikey: YOUR_API_KEY_HERE" \
  https://your-instance.service-now.com/api/now/table/sys_user?sysparm_limit=1
```

Replace:
- `YOUR_API_KEY_HERE` with the token copied from Step 2
- `your-instance.service-now.com` with your ServiceNow instance URL

## Error Handling

The server validates all required parameters and returns meaningful error messages:

- Empty employee ID, name, business justification, or preferred model will raise `ValueError`
- All successful ticket creations return formatted ticket details
- Health check endpoint available at `/health`

## Attribution

The ServiceNow integration code in `src/snow/servicenow/` is based on the work from the [servicenow-mcp](https://github.com/echelon-ai-labs/servicenow-mcp) project by Echelon AI Labs. We acknowledge and appreciate their contribution to the ServiceNow MCP implementation.