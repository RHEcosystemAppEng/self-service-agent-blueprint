# Mock ServiceNow Server

A lightweight mock ServiceNow server that provides compatible REST API endpoints for testing and development of the ServiceNow MCP server.

## Overview

This mock server implements the same REST API endpoints as ServiceNow, allowing the MCP server to work seamlessly without requiring a real ServiceNow instance. The server uses the same mock data that was previously embedded in the MCP server code.

## Key Features

- **API Compatibility**: Implements ServiceNow REST API endpoints with identical request/response formats
- **Authentication**: Supports ServiceNow API key authentication via `x-sn-apikey` header
- **Mock Data**: Pre-populated with test employee and laptop data
- **Container Ready**: Containerized using standardized template for easy deployment in Kubernetes environments
- **FastAPI Based**: Built with FastAPI for performance and automatic API documentation

## Supported Endpoints

### Service Catalog - Laptop Refresh Requests
- **POST** `/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now`
  - Create laptop refresh tickets
  - Matches ServiceNow service catalog API format

### User Management
- **GET** `/api/now/table/sys_user`
  - Look up users by email
  - Returns user data including sys_id, name, location

### Asset Management
- **GET** `/api/now/table/cmdb_ci_computer`
  - Look up computers assigned to users
  - Returns laptop/computer details including model, serial, warranty

## Configuration

The mock server is configured via environment variables:

- `PORT`: Server port (default: 8080)
- `HOST`: Server host (default: 0.0.0.0)
- `LOG_LEVEL`: Logging level (default: INFO)

## Mock Data

The server includes mock data for several test employees and their assigned laptops:
- alice.johnson@company.com
- john.doe@company.com
- maria.garcia@company.com
- And several others...

## Usage

### Local Development
```bash
cd mock-service-now
uv run uvicorn src.mock_servicenow.server:app --host 0.0.0.0 --port 8080
```

### Container Build
```bash
# Build using the standardized template from project root
podman build -f mock-service-now/Containerfile \
  --build-arg SERVICE_NAME=mock-service-now \
  --build-arg MODULE_NAME=mock_servicenow.server \
  -t mock-servicenow .

# Or use the Makefile from project root
make build-mock-servicenow-image

# Run the container
podman run -p 8080:8080 mock-servicenow
```

### With MCP Server
Set the MCP server's `SERVICENOW_INSTANCE_URL` to point to the mock server:
```bash
export SERVICENOW_INSTANCE_URL="http://mock-servicenow:8080"
```

## API Documentation

Once running, visit `http://localhost:8080/docs` for interactive API documentation.

## Testing

Run tests with:
```bash
cd mock-service-now
uv run python -m pytest tests/
```

## Integration with Self-Service Agent

This mock server is automatically deployed when using:
```bash
make helm-install-test NAMESPACE=your-namespace
```

The MCP server will automatically use the mock server when `SERVICENOW_INSTANCE_URL` is set to the mock server's URL.