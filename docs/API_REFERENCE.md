# API Reference

Complete API documentation for the Self-Service Agent system based on the actual codebase implementation.

## Table of Contents

1. [Base URLs](#base-urls)
2. [Authentication](#authentication)
3. [Request Manager Endpoints](#request-manager-endpoints)
4. [Integration Dispatcher Endpoints](#integration-dispatcher-endpoints)
5. [Request/Response Schemas](#requestresponse-schemas)
6. [Error Responses](#error-responses)
7. [Health Checks](#health-checks)

## Base URLs

### Request Manager
- **Local Development**: `http://localhost:8080` (with port-forward)
- **Production**: `https://your-request-manager-url`

### Integration Dispatcher
- **Local Development**: `http://localhost:8081` (with port-forward)
- **Production**: `https://your-integration-dispatcher-url`

## Authentication

### JWT Authentication
```http
Authorization: Bearer <jwt-token>
```

### API Key Authentication
```http
Authorization: Bearer <api-key>
```

### Tool API Key Authentication
```http
x-api-key: <tool-api-key>
```

### Slack Signature Verification
```http
x-slack-signature: <signature>
x-slack-request-timestamp: <timestamp>
```

### Legacy Header Authentication
```http
x-user-id: <user-id>
x-user-email: <email>
x-user-groups: <comma-separated-groups>
```

## Request Manager Endpoints

### POST /api/v1/requests/web

Handle web-based requests with authentication.

**Authentication**: Required (JWT or API Key)

**Request Body**:
```json
{
  "user_id": "string",
  "content": "string",
  "client_ip": "string" (optional)
}
```

**Response**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "status": "completed",
  "response": {
    "content": "string",
    "agent_id": "string",
    "metadata": {},
    "processing_time_ms": 0,
    "requires_followup": false,
    "followup_actions": []
  }
}
```

**Example**:
```bash
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Authorization: Bearer web-test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "web-test-user",
    "content": "I need help with my laptop",
    "client_ip": "192.168.1.100"
  }'
```

### POST /api/v1/requests/cli

Handle CLI tool requests with authentication.

**Authentication**: Required (JWT or API Key)

**Request Body**:
```json
{
  "user_id": "string",
  "content": "string",
  "metadata": {
    "terminal": "string" (optional),
    "command": "string" (optional)
  }
}
```

**Response**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "status": "completed",
  "response": {
    "content": "string",
    "agent_id": "string",
    "metadata": {},
    "processing_time_ms": 0,
    "requires_followup": false,
    "followup_actions": []
  }
}
```

**Example**:
```bash
curl -X POST https://your-request-manager/api/v1/requests/cli \
  -H "Authorization: Bearer cli-user" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "cli-user",
    "content": "Check my system status",
    "metadata": {
      "terminal": "bash",
      "command": "systemctl status"
    }
  }'
```

### POST /api/v1/requests/tool

Handle system-to-system tool requests.

**Authentication**: Required (Tool API Key)

**Request Body**:
```json
{
  "user_id": "string",
  "content": "string",
  "tool_id": "string",
  "tool_instance_id": "string" (optional),
  "trigger_event": "string",
  "tool_context": {
    "key": "value"
  } (optional),
  "metadata": {
    "correlation_id": "string" (optional),
    "automation_rule": "string" (optional),
    "triggered_by": "string" (optional)
  } (optional)
}
```

**Response**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "status": "completed",
  "response": {
    "content": "string",
    "agent_id": "string",
    "metadata": {},
    "processing_time_ms": 0,
    "requires_followup": false,
    "followup_actions": []
  }
}
```

**Example**:
```bash
curl -X POST https://your-request-manager/api/v1/requests/tool \
  -H "x-api-key: snow-integration-key" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice.johnson",
    "content": "Automated notification: Laptop refresh due",
    "tool_id": "snow-integration",
    "trigger_event": "asset.refresh.due",
    "tool_context": {
      "asset_tag": "LAPTOP-12345",
      "target_agent_id": "laptop-refresh-agent"
    }
  }'
```

### POST /api/v1/requests/generic

Handle generic requests without authentication.

**Authentication**: None

**Request Body**:
```json
{
  "integration_type": "string",
  "user_id": "string",
  "content": "string"
}
```

**Response**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "status": "completed",
  "response": {
    "content": "string",
    "agent_id": "string",
    "metadata": {},
    "processing_time_ms": 0,
    "requires_followup": false,
    "followup_actions": []
  }
}
```

**Example**:
```bash
curl -X POST https://your-request-manager/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "web",
    "user_id": "anonymous-user",
    "content": "Test message"
  }'
```

### Conversation Management

**All endpoints use LangGraph state machine** for advanced conversation management with persistent thread management and context.

**Supported Endpoints**:
- `/api/v1/requests/web` - Web interface
- `/api/v1/requests/cli` - CLI tool
- `/api/v1/requests/tool` - Tool integration
- `/api/v1/requests/generic` - Generic requests

**Request Body**:
```json
{
  "user_id": "string",
  "content": "string",
  "request_manager_session_id": "string" (optional),
  "user_email": "string" (optional),
  "session_name": "string" (optional),
  "metadata": {} (optional)
}
```

**Response**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "status": "completed",
  "response": {
    "content": "string",
    "agent_id": "string",
    "metadata": {},
    "processing_time_ms": 0,
    "requires_followup": false,
    "followup_actions": []
  }
}
```

**Example** (Web endpoint):
```bash
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token" \
  -d '{
    "user_id": "user123",
    "content": "I need help with my laptop",
    "user_email": "user@example.com",
    "session_name": "Laptop Support Session"
  }'
```

### POST /api/v1/events/cloudevents

Handle incoming CloudEvents from Integration Dispatcher and Agent Service.

**Authentication**: None

**Request Body**: CloudEvent format

**Supported Event Types**:
- `com.self-service-agent.request.created` - Request events from Integration Dispatcher (Slack/Email)
- `com.self-service-agent.agent.response-ready` - Agent response events from Agent Service

**Response**:
```json
{
  "status": "success",
  "message": "CloudEvent processed"
}
```

**Note:** This endpoint handles internal service-to-service communication via CloudEvents. External clients should use `/api/v1/requests/*` endpoints instead.

### GET /health

Health check endpoint for Request Manager.

**Authentication**: None

**Response**:
```json
{
  "status": "healthy",
  "service": "request-manager",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Integration Dispatcher Endpoints

### Slack Endpoints

#### POST /slack/events
Handle Slack events (messages, mentions, etc.).

**Authentication**: Required (Slack Signature Verification)

**Request Body**: Slack event payload

**Response**:
```json
{
  "status": "ok"
}
```

#### POST /slack/interactive
Handle Slack interactive components (buttons, modals, etc.).

**Authentication**: Required (Slack Signature Verification)

**Request Body**: Slack interactive payload

**Response**:
```json
{
  "text": "Response text"
}
```

#### POST /slack/commands
Handle Slack slash commands.

**Authentication**: Required (Slack Signature Verification)

**Request Body**: Slack slash command payload

**Response**:
```json
{
  "text": "Response text"
}
```

### Delivery Endpoints

#### POST /deliver
Handle direct delivery requests.

**Authentication**: None

**Request Body**:
```json
{
  "request_id": "string",
  "session_id": "string",
  "user_id": "string",
  "agent_id": "string",
  "subject": "string",
  "content": "string",
  "template_variables": {}
}
```

**Response**:
```json
{
  "status": "success",
  "request_id": "string",
  "deliveries": []
}
```

### CloudEvent Endpoints

#### POST /notifications

Handle notification CloudEvents (request acknowledgments, status updates).

**Authentication**: None

**Request Body**: CloudEvent format

**Response**:
```json
{
  "status": "success",
  "message": "Notification processed"
}
```

### GET /api/v1/integration-defaults

Get system-wide integration default configurations.

**Authentication**: None

**Response**:
```json
{
  "default_integrations": {
    "SLACK": {
      "enabled": true,
      "priority": 1,
      "retry_count": 3,
      "retry_delay_seconds": 60,
      "config": {
        "thread_replies": false,
        "mention_user": false,
        "include_agent_info": true
      }
    },
    "EMAIL": {
      "enabled": true,
      "priority": 2,
      "retry_count": 3,
      "retry_delay_seconds": 60,
      "config": {
        "include_agent_info": true
      }
    }
  }
}
```

### GET /api/v1/users/{user_id}/integration-defaults

Get user's effective integration configuration.

**Authentication**: None

**Response**:
```json
{
  "user_id": "string",
  "user_overrides": {
    "EMAIL": {
      "enabled": true,
      "priority": 1,
      "retry_count": 5,
      "retry_delay_seconds": 30,
      "config": {
        "email_address": "user@company.com",
        "format": "html"
      }
    }
  },
  "effective_configs": {
    "EMAIL": {
      "enabled": true,
      "priority": 1,
      "retry_count": 5,
      "retry_delay_seconds": 30,
      "config": {
        "email_address": "user@company.com",
        "format": "html"
      }
    },
    "SLACK": {
      "enabled": true,
      "priority": 1,
      "retry_count": 3,
      "retry_delay_seconds": 60,
      "config": {
        "thread_replies": false,
        "mention_user": false,
        "include_agent_info": true
      }
    }
  },
  "using_integration_defaults": false
}
```

### POST /api/v1/users/{user_id}/integrations

Create or update user integration configuration.

**Authentication**: None

**Request Body**:
```json
{
  "integration_type": "EMAIL",
  "enabled": true,
  "config": {
    "email_address": "user@company.com",
    "format": "html"
  },
  "priority": 1,
  "retry_count": 5,
  "retry_delay_seconds": 30
}
```

**Response**:
```json
{
  "id": 1,
  "user_id": "string",
  "integration_type": "EMAIL",
  "enabled": true,
  "priority": 1,
  "retry_count": 5,
  "retry_delay_seconds": 30,
  "config": {
    "email_address": "user@company.com",
    "format": "html"
  },
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### PUT /api/v1/users/{user_id}/integrations/{integration_type}

Update user integration configuration.

**Authentication**: None

**Request Body**:
```json
{
  "enabled": false,
  "retry_count": 10
}
```

**Response**:
```json
{
  "id": 1,
  "user_id": "string",
  "integration_type": "EMAIL",
  "enabled": false,
  "priority": 1,
  "retry_count": 10,
  "retry_delay_seconds": 30,
  "config": {
    "email_address": "user@company.com",
    "format": "html"
  },
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### DELETE /api/v1/users/{user_id}/integrations/{integration_type}

Delete user integration configuration.

**Authentication**: None

**Response**:
```json
{
  "status": "success",
  "message": "Integration configuration deleted"
}
```

### POST /api/v1/users/{user_id}/integration-defaults/reset

Reset user to system integration defaults.

**Authentication**: None

**Response**:
```json
{
  "status": "success",
  "message": "User configuration reset to defaults"
}
```

### GET /api/v1/users/{user_id}/integrations

List user's custom integration configurations.

**Authentication**: None

**Response**:
```json
{
  "user_id": "string",
  "integrations": [
    {
      "id": 1,
      "integration_type": "EMAIL",
      "enabled": true,
      "priority": 1,
      "retry_count": 5,
      "retry_delay_seconds": 30,
      "config": {
        "email_address": "user@company.com",
        "format": "html"
      },
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### GET /api/v1/users/{user_id}/deliveries

Get user's delivery history.

**Authentication**: None

**Query Parameters**:
- `limit` (optional): Number of records to return (default: 50)
- `offset` (optional): Number of records to skip for pagination (default: 0)

**Response**:
```json
[
  {
    "id": 1,
    "request_id": "string",
    "session_id": "string",
    "user_id": "string",
    "integration_type": "EMAIL",
    "subject": "string",
    "content": "string",
    "status": "DELIVERED",
    "error_message": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

### GET /health

Health check endpoint for Integration Dispatcher.

**Authentication**: None

**Response**:
```json
{
  "status": "healthy",
  "service": "integration-dispatcher",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Request/Response Schemas

### Integration Types

```typescript
enum IntegrationType {
  SLACK = "SLACK",
  WEB = "WEB",
  CLI = "CLI",
  TOOL = "TOOL",
  EMAIL = "EMAIL",
  SMS = "SMS",
  WEBHOOK = "WEBHOOK",
  TEAMS = "TEAMS",
  DISCORD = "DISCORD",
  TEST = "TEST"
}
```

### Session Status

```typescript
enum SessionStatus {
  ACTIVE = "ACTIVE",
  INACTIVE = "INACTIVE",
  EXPIRED = "EXPIRED",
  ARCHIVED = "ARCHIVED"
}
```

### Delivery Status

```typescript
enum DeliveryStatus {
  PENDING = "PENDING",
  DELIVERED = "DELIVERED",
  FAILED = "FAILED",
  RETRYING = "RETRYING",
  EXPIRED = "EXPIRED"
}
```

### Normalized Request

```typescript
interface NormalizedRequest {
  request_id: string;
  session_id: string;
  user_id: string;
  integration_type: IntegrationType;
  request_type: string;
  content: string;
  integration_context: Record<string, any>;
  user_context: Record<string, any>;
  target_agent_id?: string;
  requires_routing: boolean;
  created_at: string;
}
```

### Delivery Request

```typescript
interface DeliveryRequest {
  request_id: string;
  session_id: string;
  user_id: string;
  agent_id: string;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
}
```

## Error Responses

All error responses follow the `ErrorResponse` schema with `error`, `error_code`, and optional `request_id` fields.

### 400 Bad Request
```json
{
  "error": "Validation failed",
  "error_code": "HTTP_400",
  "request_id": "optional-request-id"
}
```

### 401 Unauthorized
```json
{
  "error": "Authentication required",
  "error_code": "HTTP_401"
}
```

### 403 Forbidden
```json
{
  "error": "User ID mismatch",
  "error_code": "HTTP_403"
}
```

### 404 Not Found
```json
{
  "error": "Resource not found",
  "error_code": "HTTP_404"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "error_code": "INTERNAL_ERROR"
}
```

## Health Checks

Both Request Manager and Integration Dispatcher provide two health check endpoints:

### GET /health

Lightweight health check without database dependency. Returns basic service status:
- `status`: Service health status
- `service`: Service name
- `version`: Service version
- `timestamp`: Current timestamp

### GET /health/detailed

Detailed health check with database connectivity verification. Returns:
- `status`: Service health status
- `timestamp`: Current timestamp
- `version`: Service version
- `database_connected`: Database connectivity status
- `services`: Additional service-specific status information

**Note:** The simple `/health` endpoint is recommended for container liveness probes as it doesn't depend on database connectivity.

### Integration Availability

The Integration Dispatcher's `/health/detailed` endpoint includes integration availability information. The system automatically determines which integrations are available based on:

- **SLACK**: Bot token and signing secret configuration
- **EMAIL**: SMTP server configuration
- **TEST**: Test integration configuration
- **WEBHOOK**: Always available (no health check)
- **SMS**: Not implemented (always disabled)

## Related Documentation

- [Integration Guide](../guides/INTEGRATION_GUIDE.md) - Complete integration and request management guide
- [Safety Shields Guide](../guides/SAFETY_SHIELDS_GUIDE.md) - Content moderation and safety configuration
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - System architecture and flow diagrams
- [Authentication Guide](../guides/AUTHENTICATION_GUIDE.md) - Authentication setup and configuration