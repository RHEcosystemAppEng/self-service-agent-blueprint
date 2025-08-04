# MCP Servers for Self-Service Agent

This directory contains MCP (Model Context Protocol) servers that provide tools for employee information lookup and ServiceNow integration.

## Services

### Employee Info Server (`employee-info/`)
Provides employee information lookup including laptop age tracking.

**Available Tools:**
- `lookup_employee_info` - Look up employee information by ID or email
- `get_laptop_age` - Get laptop age information for a specific employee
- `list_employees_with_old_laptops` - List employees with laptops older than specified days

**Sample Data:**
- EMP001: John Doe (Dell Latitude 7420, 682 days old)
- EMP002: Jane Smith (MacBook Pro 14-inch, 797 days old)
- EMP003: Bob Johnson (ThinkPad X1 Carbon, 390 days old)
- EMP004: Alice Brown (HP EliteBook 840 G9, 1278 days old)

### ServiceNow Server (`servicenow/`)
Provides laptop request management functionality.

**Available Tools:**
- `submit_laptop_request` - Submit a new laptop request
- `check_request_status` - Check status of a laptop request by ID or employee
- `list_all_requests` - List all requests with optional status/employee filtering
- `update_request_status` - Update request status (admin function)

**Request Types:**
- `new` - New hire equipment
- `replacement` - Replace existing laptop
- `upgrade` - Upgrade current laptop

## Quick Start

### Local Development with Podman

Use the provided script to start both MCP servers locally:

```bash
# Start all servers
./scripts/start-mcp-servers.sh start

# Check status
./scripts/start-mcp-servers.sh status

# View logs
./scripts/start-mcp-servers.sh logs

# Stop servers
./scripts/start-mcp-servers.sh stop
```

**Service URLs:**
- Employee Info: http://localhost:8001
- ServiceNow: http://localhost:8002

### Kubernetes Deployment

Deploy using the Helm chart:

```bash
# Install the MCP servers
helm install mcp-servers ./mcp-servers/helm \
  --namespace mcp-servers \
  --create-namespace

# Check status
kubectl get pods -n mcp-servers

# Port forward for testing
kubectl port-forward -n mcp-servers svc/mcp-employee-info 8001:8000
kubectl port-forward -n mcp-servers svc/mcp-servicenow 8002:8000
```

## Configuration

### Helm Values

Configure the servers in `helm/values.yaml`:

```yaml
mcp-servers:
  mcp-employee-info:
    deploy: true
    imageRepository: quay.io/ecosystem-appeng/mcp-employee-info
    replicas: 1
    
  mcp-servicenow:
    deploy: true
    imageRepository: quay.io/ecosystem-appeng/mcp-servicenow
    replicas: 1
```

### Environment Variables

**Employee Info Server:**
- `LOG_LEVEL` - Logging level (default: INFO)

**ServiceNow Server:**
- `LOG_LEVEL` - Logging level (default: INFO)
- `SERVICENOW_INSTANCE` - ServiceNow instance URL (for real integration)
- `SERVICENOW_USERNAME` - ServiceNow username (for real integration)
- `SERVICENOW_PASSWORD` - ServiceNow password (for real integration)

## Usage Examples

### Employee Info Lookup

```python
# Look up employee by ID
{
  "tool": "lookup_employee_info",
  "arguments": {"employee_id": "EMP001"}
}

# Get laptop age
{
  "tool": "get_laptop_age", 
  "arguments": {"employee_id": "EMP001"}
}

# Find employees with old laptops (>2 years)
{
  "tool": "list_employees_with_old_laptops",
  "arguments": {"max_age_days": 730}
}
```

### ServiceNow Requests

```python
# Submit laptop request
{
  "tool": "submit_laptop_request",
  "arguments": {
    "employee_id": "EMP005",
    "employee_name": "New Employee", 
    "employee_email": "new.employee@company.com",
    "request_type": "new",
    "laptop_preference": "MacBook Pro 14-inch",
    "justification": "New hire equipment setup"
  }
}

# Check request status
{
  "tool": "check_request_status",
  "arguments": {"request_id": "REQ001"}
}

# List all pending requests
{
  "tool": "list_all_requests",
  "arguments": {"status": "submitted"}
}
```

## Health Checks

Both servers provide health endpoints:
- `GET /health` - Returns service health status

## Development

### Building Images

```bash
# Employee Info Server
cd mcp-servers/employee-info
podman build -t mcp-employee-info:latest .

# ServiceNow Server  
cd mcp-servers/servicenow
podman build -t mcp-servicenow:latest .
```

### Running Locally

```bash
# Employee Info Server
cd mcp-servers/employee-info
python server.py

# ServiceNow Server
cd mcp-servers/servicenow  
python server.py
```

## Integration with Self-Service Agent

Configure the main agent to use these MCP servers by updating the Llama Stack configuration to include the MCP server URIs:

```yaml
mcp_servers:
  - name: employee-info
    uri: http://mcp-employee-info:8000/sse
  - name: servicenow
    uri: http://mcp-servicenow:8000/sse
```