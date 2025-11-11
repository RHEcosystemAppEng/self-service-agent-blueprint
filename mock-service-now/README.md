# Mock ServiceNow API

A standalone mock ServiceNow API service that mimics real ServiceNow behavior for testing and CI environments.

## Purpose

This service allows for homogeneous code that doesn't need to distinguish between mock and real ServiceNow instances. The client code only needs to know a `SERVICENOW_INSTANCE_URL` - whether it points to a real ServiceNow instance or this mock service is transparent to the application.

## Features

- **Realistic API Endpoints**: Implements key ServiceNow REST API endpoints:
  - `/api/now/table/sys_user` - User management
  - `/api/now/table/cmdb_ci_computer` - Computer/asset management
  - `/api/sn_sc/servicecatalog/items/{item_id}/order_now` - Service catalog orders

- **Authentic Response Format**: Returns JSON responses that match the exact structure of real ServiceNow APIs, including:
  - Nested `result` arrays
  - `display_value` fields for reference fields
  - Proper ServiceNow sys_id format (32-character hex)

- **Authentication Support**: Simulates ServiceNow authentication:
  - Basic Authentication
  - API Key authentication via `X-ServiceNow-API-Key` header

- **Query Parameter Support**: Handles standard ServiceNow query parameters:
  - `sysparm_query` - Filter conditions
  - `sysparm_fields` - Field selection
  - `sysparm_limit` - Result limiting
  - `sysparm_display_value` - Display value formatting

## Running the Service

### Development
```bash
cd mock-service-now
uv sync
uv run python src/mock_service_now/main.py
```

### Docker
```bash
# Build the image
docker build -f mock-service-now/Containerfile -t mock-service-now .

# Run the container
docker run -p 8082:8082 mock-service-now
```

The service will be available at `http://localhost:8082`.

## API Endpoints

### Health Check
```
GET /health
```

### User Lookup
```
GET /api/now/table/sys_user?sysparm_query=email=user@example.com&sysparm_fields=sys_id,name,email,location
```

### Computer Lookup
```
GET /api/now/table/cmdb_ci_computer?sysparm_query=assigned_to=user_sys_id&sysparm_fields=sys_id,name,model_id,serial_number
```

### Service Catalog Order
```
POST /api/sn_sc/servicecatalog/items/{item_id}/order_now
Content-Type: application/json

{
  "sysparm_quantity": 1,
  "variables": {
    "laptop_choices": "apple_mac_book_air_m_3",
    "who_is_this_request_for": "user_sys_id"
  }
}
```

### Debug Endpoints
For testing and development:

```
GET /debug/users     # List all mock users
GET /debug/computers # List all mock computers
POST /reset          # Reset service to initial state
```

## Mock Data

The service includes realistic mock data for several users with different:
- Locations (EMEA, LATAM, APAC, NA)
- Laptop models (MacBook, ThinkPad, Dell, HP)
- Purchase dates and warranty statuses
- ServiceNow-formatted sys_ids

## Authentication

The service requires authentication like real ServiceNow. Example:

```bash
# Basic auth
curl -u "username:password" http://localhost:8082/api/now/table/sys_user

# API key
curl -H "X-ServiceNow-API-Key: your-api-key" http://localhost:8082/api/now/table/sys_user
```

## Integration

To use this mock instead of real ServiceNow, simply point your `SERVICENOW_INSTANCE_URL` to this service:

```bash
# For real ServiceNow
export SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com

# For mock ServiceNow
export SERVICENOW_INSTANCE_URL=http://localhost:8082
```

No code changes required - the application will work identically with both real and mock instances.