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
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "message": "string"
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
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "message": "string"
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
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "message": "string",
  "agent_response": {
    "agent_id": "string",
    "estimated_completion": "string",
    "next_steps": ["string"]
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
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "message": "string"
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
- `/api/v1/requests/slack` - Slack integration
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
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "response": {
    "content": "string",
    "agent_id": "string",
    "conversation_thread_id": "string",
    "metadata": {}
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

### POST /api/v1/requests/slack

Handle Slack integration requests with signature verification.

**Authentication**: Required (Slack Signature Verification)

**Request Body**:
```json
{
  "user_id": "string",
  "content": "string",
  "channel_id": "string",
  "thread_id": "string" (optional),
  "slack_user_id": "string",
  "slack_team_id": "string"
}
```

**Response**:
```json
{
  "status": "success",
  "request_id": "string",
  "session_id": "string",
  "message": "string"
}
```

**Example**:
```bash
curl -X POST https://your-request-manager/api/v1/requests/slack \
  -H "x-slack-signature: <signature>" \
  -H "x-slack-request-timestamp: <timestamp>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "U123456789",
    "content": "Hello",
    "channel_id": "C123456789",
    "slack_user_id": "U123456789",
    "slack_team_id": "T123456789"
  }'
```

### POST /api/v1/events/cloudevents

Handle incoming CloudEvents (e.g., from agent responses).

**Authentication**: None

**Request Body**: CloudEvent format

**Response**:
```json
{
  "status": "success",
  "message": "CloudEvent processed"
}
```

### GET /health

Health check endpoint for Request Manager.

**Authentication**: None

**Response**:
```json
{
  "status": "healthy",
  "service": "request-manager",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z",
  "database": {
    "status": "healthy",
    "connection_pool": {
      "active": 2,
      "idle": 3,
      "max": 10
    }
  },
  "uptime": 3600
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
{
  "user_id": "string",
  "deliveries": [
    {
      "delivery_id": "string",
      "integration_type": "EMAIL",
      "status": "success",
      "created_at": "2024-01-01T00:00:00Z",
      "error_message": null
    }
  ],
  "total_count": 100,
  "limit": 50,
  "offset": 0
}
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
  "timestamp": "2024-01-01T00:00:00Z",
  "database": {
    "status": "healthy",
    "connection_pool": {
      "active": 2,
      "idle": 3,
      "max": 10
    }
  },
  "integrations_available": ["SLACK", "EMAIL", "TEST"],
  "uptime": 3600
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
  SUCCESS = "SUCCESS",
  FAILED = "FAILED",
  PENDING = "PENDING",
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

### 400 Bad Request
```json
{
  "status": "error",
  "error": "Validation failed",
  "details": {
    "field": "user_id",
    "message": "user_id is required and cannot be empty"
  }
}
```

### 401 Unauthorized
```json
{
  "status": "error",
  "error": "Authentication required",
  "details": "Invalid or missing authentication token"
}
```

### 403 Forbidden
```json
{
  "status": "error",
  "error": "Access denied",
  "details": "User ID mismatch or insufficient permissions"
}
```

### 404 Not Found
```json
{
  "status": "error",
  "error": "Resource not found",
  "details": "User or integration configuration not found"
}
```

### 500 Internal Server Error
```json
{
  "status": "error",
  "error": "Internal server error",
  "details": "An unexpected error occurred"
}
```

## Health Checks

### Request Manager Health Check

The Request Manager health check includes:
- Database connectivity
- Connection pool status
- Service uptime
- Basic service metrics

### Integration Dispatcher Health Check

The Integration Dispatcher health check includes:
- Database connectivity
- Integration availability (based on configuration)
- Service uptime
- Integration handler status

### Integration Availability

The system automatically determines which integrations are available based on:
- **SLACK**: Bot token and signing secret configuration
- **EMAIL**: SMTP server configuration
- **TEST**: Test integration configuration
- **WEBHOOK**: Always available (no health check)
- **SMS**: Not implemented (always disabled)

## Related Documentation

- [Integration Guide](INTEGRATION_GUIDE.md) - Complete integration and request management guide
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - System architecture and flow diagrams
- [Authentication Guide](AUTHENTICATION_GUIDE.md) - Authentication setup and configuration