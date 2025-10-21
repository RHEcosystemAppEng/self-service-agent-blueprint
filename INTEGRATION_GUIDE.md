# Integration Guide

This guide covers all aspects of integrating with the Self-Service Agent system, including request handling, user integration management, and delivery configuration.

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Integration Types](#integration-types)
4. [Request Processing Flow](#request-processing-flow)
5. [API Endpoints](#api-endpoints)
6. [Integration Defaults System](#integration-defaults-system)
7. [User Integration Management](#user-integration-management)
8. [Database Schema](#database-schema)
9. [Authentication](#authentication)
10. [Examples](#examples)
11. [Troubleshooting](#troubleshooting)

## Overview

The Self-Service Agent system provides a comprehensive integration layer that supports multiple communication channels and deployment modes. The system uses an **Integration Defaults** approach with **User Overrides** to provide smart defaults for all users while allowing customization when needed.

### Key Features

- **Multi-Integration Support**: Slack, Web, CLI, Tool, Email, SMS, Webhook integrations
- **Dual Conversation Modes**: Agent mode (LlamaStack) and Responses mode (LangGraph)
- **Smart Defaults**: Automatic configuration based on system health checks
- **User Overrides**: Custom configurations for specific users
- **Flexible Deployment**: Development, testing, and production modes
- **Event-Driven Architecture**: Scalable processing with Knative and CloudEvents
- **Session Management**: Persistent conversation state across interactions
- **Unified Request Processing**: Single codebase for both eventing and direct HTTP modes

## System Architecture

The system consists of three main services:

### 1. Request Manager
- **Normalizes** incoming requests from different integration types
- **Manages sessions** using PostgreSQL as a key-value store
- **Routes requests** to appropriate agents (via HTTP or CloudEvents)
- **Tracks conversation state** and request history
- **Returns responses** directly to Web/CLI/Tool/Generic integrations (synchronous HTTP responses)
- **Forwards responses** to Integration Dispatcher for delivery to Slack/Email/Webhook/Test integrations

### 2. Agent Service
- **Processes normalized requests** from the Request Manager
- **Integrates with Llama Stack** for agent interactions
- **Manages agent sessions** and conversation context
- **Publishes responses** to the broker via CloudEvents for delivery to users

### 3. Integration Dispatcher
- **Handles response delivery** to external integrations
- **Multi-tenant delivery** to Slack, Email, SMS, Webhooks
- **Manages delivery status** and retry logic
- **Supports various integration protocols**
- **Manages integration defaults** and user overrides

## Conversation Modes

The system uses LangGraph-based state machine conversations for advanced conversation management:

### Conversation Management
- **Technology**: LangGraph state machine with persistent conversation threads
- **Features**:
  - Persistent conversation threads across sessions
  - Advanced state machine-based conversation flow
  - Enhanced context management and memory
  - Support for complex multi-turn conversations
  - Intelligent agent routing and specialized task handling
  - Session-based conversation context
- **API Endpoints**: All request endpoints support conversation management
- **Best For**: Conversational AI, complex workflows, multi-turn interactions, task-oriented interactions

## Integration Types

### Bidirectional Integrations (Request + Response Delivery)
- **Slack**: Receives requests via Integration Dispatcher (`/slack/events`, `/slack/interactive`, `/slack/commands`), responses delivered via Slack API

### Request-Only Integrations (Direct Response)
- **Web**: Receives requests directly via Request Manager, responses returned directly
- **CLI**: Receives requests directly via Request Manager, responses handled synchronously by CLI tool
- **Tool**: Receives requests directly via Request Manager, responses returned immediately (notification-based)
- **Generic**: Receives requests directly via Request Manager, responses returned directly (synchronous)

### Response-Only Integrations (No Incoming Requests)
- **Email**: Only delivers responses via SMTP (no incoming email requests)
- **SMS**: Only delivers responses via SMS (no incoming SMS requests)
- **Webhook**: Only delivers responses via HTTP POST (no incoming webhook requests)
- **Test**: Only delivers responses for testing (no incoming test requests)

## Request Processing Flow

### System-Initiated Events (Slack Only)

**Production Mode (Eventing Configuration):**
```
Slack → Integration Dispatcher → Request Manager → Knative Broker → Agent Service → Integration Dispatcher → Slack
```

**Development Mode (Direct HTTP Configuration):**
```
Slack → Integration Dispatcher → Request Manager → Agent Service → Request Manager → Integration Dispatcher → Slack
```

### User-Initiated Requests (Web/CLI/Tool/Generic)

**Production Mode (Eventing Configuration):**
```
Web/CLI/Tool/Generic → Request Manager → Knative Broker → Agent Service → Integration Dispatcher → Slack/Email/Webhook/Test
```

**Development Mode (Direct HTTP Configuration):**
```
Web/CLI/Tool/Generic → Request Manager → Agent Service → Request Manager → Integration Dispatcher → Slack/Email/Webhook/Test
```

## API Endpoints

### Request Endpoints

#### Web Requests
```http
POST /api/v1/requests/web
Authorization: Bearer <jwt-token-or-api-key>
Content-Type: application/json

{
  "user_id": "string",
  "content": "string",
  "client_ip": "string" (optional)
}
```

#### CLI Requests
```http
POST /api/v1/requests/cli
Authorization: Bearer <jwt-token-or-api-key>
Content-Type: application/json

{
  "user_id": "string",
  "content": "string",
  "metadata": {
    "terminal": "string" (optional),
    "command": "string" (optional)
  }
}
```

#### Tool Requests
```http
POST /api/v1/requests/tool
x-api-key: <tool-api-key>
Content-Type: application/json

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

#### Generic Requests
```http
POST /api/v1/requests/generic
Content-Type: application/json

{
  "integration_type": "string",
  "user_id": "string",
  "content": "string"
}
```

#### Slack Requests
```http
POST /api/v1/requests/slack
x-slack-signature: <signature>
x-slack-request-timestamp: <timestamp>
Content-Type: application/json

{
  "user_id": "string",
  "content": "string",
  "channel_id": "string",
  "thread_id": "string" (optional),
  "slack_user_id": "string",
  "slack_team_id": "string"
}
```

### Integration Management Endpoints

#### Get System Integration Defaults
```http
GET /api/v1/integration-defaults
```

#### Get User's Effective Configuration
```http
GET /api/v1/users/{user_id}/integration-defaults
```

#### Create User Override
```http
POST /api/v1/users/{user_id}/integrations
Content-Type: application/json

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

#### Update User Override
```http
PUT /api/v1/users/{user_id}/integrations/{integration_type}
Content-Type: application/json

{
  "enabled": false,
  "retry_count": 10
}
```

#### Delete User Override
```http
DELETE /api/v1/users/{user_id}/integrations/{integration_type}
```

#### Reset User to Defaults
```http
POST /api/v1/users/{user_id}/integration-defaults/reset
```

#### Get Delivery History
```http
GET /api/v1/users/{user_id}/deliveries?limit=20&offset=0
```

### Health and Monitoring
```http
GET /health
```

## Integration Defaults System

The system uses a **two-tier configuration approach**:

1. **Integration Defaults** - System-wide default configurations for all integrations
2. **User Overrides** - Custom configurations that override defaults for specific users

### How It Works

```
User Request → Check User Overrides → Fall back to Integration Defaults → Deliver
```

- If a user has **custom configurations**, those are used
- If a user has **no custom configurations**, system defaults are used (lazy approach)
- Users can have **partial overrides** (e.g., only EMAIL configured, others use defaults)

### Supported Integration Types

| Integration | Default Priority | Default Retry | Auto-Enabled |
|-------------|------------------|---------------|--------------|
| **SLACK** | 1 (highest) | 3 retries, 60s delay | ✅ If configured |
| **EMAIL** | 2 | 3 retries, 60s delay | ✅ If SMTP configured |
| **WEBHOOK** | 3 | 1 retry, 30s delay | ❌ Always disabled |
| **SMS** | 4 | 2 retries, 45s delay | ❌ Always disabled |
| **TEST** | 5 (lowest) | 1 retry, 10s delay | ✅ If configured |

**Note**: CLI and TOOL integrations are handled directly by the Request Manager and do not use the Integration Dispatcher for delivery.

### Default Configuration Examples

#### SLACK Defaults
```json
{
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
```

#### EMAIL Defaults
```json
{
  "enabled": true,
  "priority": 2,
  "retry_count": 3,
  "retry_delay_seconds": 60,
  "config": {
    "include_agent_info": true
  }
}
```

## User Integration Management

### Lazy Integration Approach

The system uses a **lazy approach** for integration defaults:

- **No database entries** are created for users who don't need custom overrides
- **Smart defaults** are applied dynamically without persistence
- **User configs** are only created when users explicitly override defaults
- **Better performance** - fewer database queries and no constraint violations

### User Configuration Examples

#### User with Custom EMAIL Configuration
```json
{
  "user_id": "john.doe",
  "user_overrides": {
    "EMAIL": {
      "enabled": true,
      "priority": 1,
      "retry_count": 5,
      "retry_delay_seconds": 30,
      "config": {
        "email_address": "john.doe@company.com",
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
        "email_address": "john.doe@company.com",
        "format": "html"
      }
    }
  },
  "using_integration_defaults": false
}
```

#### User with No Custom Configurations
```json
{
  "user_id": "jane.doe",
  "user_overrides": {},
  "effective_configs": {
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
        "format": "html"
      }
    }
  },
  "using_integration_defaults": true
}
```

## Database Schema

The system uses the existing `llama_agents` PostgreSQL database with these tables:

### request_sessions
```sql
- id (Integer, Primary Key)
- session_id (String(36), Unique, Indexed)
- user_id (String(255), Indexed)
- integration_type (Enum: SLACK, WEB, CLI, TOOL, EMAIL, SMS, WEBHOOK, TEAMS, DISCORD, TEST)
- status (Enum: ACTIVE, INACTIVE, EXPIRED, ARCHIVED)
- channel_id, thread_id (String(255), Optional - for Slack/Teams)
- external_session_id (String(255), Optional)
- current_agent_id (String(255), Optional)
- llama_stack_session_id (String(255), Optional)
- integration_metadata (JSON)
- user_context (JSON)
- conversation_context (JSON)
- total_requests (Integer, Default: 0)
- last_request_id (String(36), Optional)
- last_request_at (Timestamp, Optional)
- expires_at (Timestamp, Optional)
- created_at, updated_at (Timestamps)
```

### request_logs
```sql
- id (Integer, Primary Key)
- request_id (String(36), Unique, Indexed)
- session_id (String(36), Foreign Key to request_sessions.session_id, Indexed)
- request_type (String(50))
- request_content (Text)
- normalized_request (JSON)
- agent_id (String(255), Optional)
- processing_time_ms (Integer, Optional)
- response_content (Text, Optional)
- response_metadata (JSON)
- cloudevent_id (String(36), Optional)
- cloudevent_type (String(100), Optional)
- created_at, updated_at, completed_at (Timestamps)
```

### user_integration_configs
```sql
- id (Integer, Primary Key)
- user_id (String(255), Indexed)
- integration_type (Enum: SLACK, EMAIL, SMS, WEBHOOK, TEST)
- enabled (Boolean, Default: true)
- priority (Integer, Default: 1)
- retry_count (Integer, Default: 3)
- retry_delay_seconds (Integer, Default: 60)
- config (JSON)
- created_at, updated_at (Timestamps)
```

### integration_default_configs
```sql
- id (Integer, Primary Key)
- integration_type (Enum: SLACK, EMAIL, SMS, WEBHOOK, TEST)
- enabled (Boolean, Default: true)
- priority (Integer, Default: 1)
- retry_count (Integer, Default: 3)
- retry_delay_seconds (Integer, Default: 60)
- config (JSON)
- created_at, updated_at (Timestamps)
```

### delivery_logs
```sql
- id (Integer, Primary Key)
- delivery_id (String(36), Unique, Indexed)
- user_id (String(255), Indexed)
- integration_type (Enum: SLACK, EMAIL, SMS, WEBHOOK, TEST)
- status (Enum: SUCCESS, FAILED, PENDING, RETRYING, EXPIRED)
- error_message (Text, Optional)
- created_at, updated_at (Timestamps)
```

## Authentication

### JWT Authentication
```bash
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{"user_id": "john.doe", "content": "Hello"}'
```

### API Key Authentication
```bash
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Authorization: Bearer web-test-user" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "web-test-user", "content": "Hello"}'
```

### Tool API Key Authentication
```bash
curl -X POST https://your-request-manager/api/v1/requests/tool \
  -H "x-api-key: your-tool-api-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user", "content": "Tool request", "tool_id": "snow-integration"}'
```

### Slack Signature Verification
```bash
curl -X POST https://your-request-manager/api/v1/requests/slack \
  -H "x-slack-signature: <signature>" \
  -H "x-slack-request-timestamp: <timestamp>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "U123456789", "content": "Hello", "channel_id": "C123456789", "slack_user_id": "U123456789", "slack_team_id": "T123456789"}'
```

## Examples

### Python Integration Example

```python
import httpx
from shared_clients import RequestManagerClient

async def send_request():
    # Using the shared request manager client
    client = RequestManagerClient(
        request_manager_url="https://your-request-manager",
        user_id="john.doe"
    )
    
    try:
        # Add API key to headers
        client.client.headers.update({
            "Authorization": "Bearer web-test-user"
        })
        
        response = await client.send_request(
            content="Hello, I need help with my laptop",
            integration_type="WEB",
            endpoint="web",
            metadata={
                "client_ip": "192.168.1.100"
            }
        )
        return response
    finally:
        await client.close()
```

### Bash Integration Example

```bash
#!/bin/bash

BASE_URL="https://your-request-manager"
API_KEY="web-test-user"

curl -X POST "$BASE_URL/api/v1/requests/web" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$API_KEY'",
    "content": "System status check",
    "client_ip": "192.168.1.100"
  }'
```

### User Configuration Management Example

```python
import httpx

async def configure_user_email(user_id: str, email: str):
    async with httpx.AsyncClient() as client:
        # Create email override for user
        response = await client.post(
            f"http://localhost:8080/api/v1/users/{user_id}/integrations",
            json={
                "integration_type": "EMAIL",
                "enabled": True,
                "config": {
                    "email_address": email,
                    "format": "html"
                },
                "priority": 1,
                "retry_count": 5,
                "retry_delay_seconds": 30
            }
        )
        return response.json()

# Usage
await configure_user_email("john.doe", "john.doe@company.com")
```

## Troubleshooting

### Common Issues

#### 1. User not receiving notifications
- Check user's effective configuration: `GET /api/v1/users/{user_id}/integration-defaults`
- Check delivery logs: `GET /api/v1/users/{user_id}/deliveries`
- Verify integration health: `GET /health`

#### 2. Integration not working
- Check system defaults: `GET /api/v1/integration-defaults`
- Verify integration is enabled in defaults
- Check if user has disabled override

#### 3. Authentication failures
- Verify API key is correct
- Ensure JWT token is valid
- Check authentication configuration

### Debug Commands

```bash
# Check integration health
curl http://localhost:8080/health

# Check system defaults
curl http://localhost:8080/api/v1/integration-defaults

# Check user configuration
curl http://localhost:8080/api/v1/users/john.doe/integration-defaults

# Check delivery history
curl http://localhost:8080/api/v1/users/john.doe/deliveries

# Reset user to defaults
curl -X POST http://localhost:8080/api/v1/users/john.doe/integration-defaults/reset
```

### Best Practices

1. **Use Integration Defaults** - Let the system handle most users automatically
2. **Override Only When Needed** - Create user overrides for special cases
3. **Monitor Delivery Logs** - Check for failed deliveries and troubleshoot
4. **Set Appropriate Priorities** - Higher priority = delivered first
5. **Configure Retry Settings** - Based on integration reliability
6. **Test After Changes** - Verify integrations work after configuration
7. **Use Descriptive User IDs** - For easier management and debugging

## Related Documentation

- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - System architecture and flows
- [Authentication Guide](AUTHENTICATION_GUIDE.md) - Authentication setup and configuration
- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Slack Setup](SLACK_SETUP.md) - Slack-specific configuration
- [Tool Integration Guide](TOOL_INTEGRATION_GUIDE.md) - Tool integration patterns