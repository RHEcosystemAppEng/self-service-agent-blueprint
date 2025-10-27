# Tool Integration Guide

This guide explains how to integrate external tools and automated systems with the Self-Service Agent system through the tool integration endpoint.

## Overview

The tool integration endpoint (`POST /api/v1/requests/tool`) enables **system-to-system communication** between external tools and the self-service agent platform. This allows automated systems to proactively trigger agent interactions and provide structured, context-rich requests.

## Table of Contents

1. [Purpose and Benefits](#purpose-and-benefits)
2. [API Endpoint Details](#api-endpoint-details)
3. [Authentication](#authentication)
4. [Request Schema](#request-schema)
5. [Example Use Cases](#example-use-cases)
6. [Integration Examples](#integration-examples)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Purpose and Benefits

### Key Benefits

- **Proactive Service**: Systems can trigger agent interactions before users report issues
- **Context-Rich Requests**: Tools provide structured data for better agent responses
- **Direct Agent Routing**: Bypass general routing by targeting specific agents
- **Automated Workflows**: Enable end-to-end automation without human intervention
- **Audit Trail**: Complete tracking of tool-generated requests and responses

### When to Use Tool Integration

- Asset management systems detecting refresh needs
- Monitoring tools flagging performance issues
- Compliance systems detecting policy violations
- HR systems triggering onboarding processes
- Scheduled maintenance workflows
- Security tools detecting anomalies

## API Endpoint Details

### Endpoint
```
POST /api/v1/requests/tool
```

### Headers
```
Content-Type: application/json
x-api-key: <your-api-key>
```

### Base URL
```
http://request-manager.<NAMESPACE>.svc.cluster.local
```

## Authentication

Tool integration uses **API key authentication** instead of JWT tokens:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key-here" \
  http://request-manager.<NAMESPACE>.svc.cluster.local/api/v1/requests/tool \
  -d '{
    "user_id": "john.doe",
    "content": "System notification",
    "tool_id": "your-tool-id",
    "trigger_event": "event.triggered"
  }'
```

### API Key Validation
- API keys are validated against the `tool_id` in the request
- Each tool must have a unique API key
- Invalid API keys result in `401 Unauthorized` response

## Request Schema

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Target user for the agent interaction |
| `content` | string | Human-readable description of the issue/request |
| `tool_id` | string | Unique identifier for the originating tool |
| `trigger_event` | string | What event triggered this request |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool_instance_id` | string | Specific instance of the tool |
| `tool_context` | object | Tool-specific structured data |
| `metadata` | object | Additional context and tracking information |

### Complete Schema

```json
{
  "user_id": "string",
  "content": "string",
  "tool_id": "string",
  "tool_instance_id": "string",
  "trigger_event": "string",
  "tool_context": {
    "key": "value"
  },
  "metadata": {
    "correlation_id": "string",
    "automation_rule": "string",
    "triggered_by": "string"
  }
}
```

## Example Use Cases

### 1. Asset Management - Laptop Refresh

**Scenario**: ServiceNow asset management detects a laptop is due for refresh based on age policy.

```json
{
  "user_id": "alice.johnson",
  "content": "Automated notification: User's laptop is due for refresh based on asset management policy. Current device is 3+ years old.",
  "tool_id": "snow-integration",
  "tool_instance_id": "snow-prod-01",
  "trigger_event": "asset.refresh.due",
  "tool_context": {
    "ticket_id": "INC0012345",
    "asset_tag": "LAPTOP-12345",
    "current_model": "Dell Latitude 7420",
    "purchase_date": "2021-01-15",
    "refresh_due_date": "2024-01-15",
    "priority": "medium",
    "target_agent_id": "laptop-refresh-agent"
  },
  "metadata": {
    "automation_rule": "3-year-refresh-policy",
    "triggered_by": "scheduled-job",
    "correlation_id": "corr-abc123"
  }
}
```

### 2. Performance Monitoring

**Scenario**: Monitoring system detects slow device performance.

```json
{
  "user_id": "bob.smith",
  "content": "Performance alert: User's laptop showing significant performance degradation over the past week.",
  "tool_id": "performance-monitor",
  "tool_instance_id": "monitor-prod-02",
  "trigger_event": "performance.degradation",
  "tool_context": {
    "device_id": "LAPTOP-67890",
    "performance_score": 2.1,
    "threshold": 3.0,
    "metrics": {
      "cpu_usage_avg": 85.2,
      "memory_usage_avg": 78.5,
      "disk_usage": 89.1
    },
    "duration": "7 days",
    "target_agent_id": "performance-troubleshooting-agent"
  },
  "metadata": {
    "alert_severity": "medium",
    "escalation_level": 1
  }
}
```

### 3. Security Compliance

**Scenario**: Security tool detects policy violation.

```json
{
  "user_id": "charlie.brown",
  "content": "Security compliance alert: User's device is missing required security patches.",
  "tool_id": "security-scanner",
  "tool_instance_id": "scanner-prod-01",
  "trigger_event": "security.patch.missing",
  "tool_context": {
    "device_id": "LAPTOP-11111",
    "missing_patches": [
      "KB5034441",
      "KB5034765"
    ],
    "risk_level": "high",
    "compliance_status": "non-compliant",
    "target_agent_id": "security-remediation-agent"
  },
  "metadata": {
    "compliance_rule": "monthly-patch-policy",
    "deadline": "2024-02-15"
  }
}
```

### 4. HR Onboarding

**Scenario**: HR system triggers device provisioning for new employee.

```json
{
  "user_id": "diana.prince",
  "content": "New employee onboarding: Device provisioning required for new hire starting next week.",
  "tool_id": "hr-system",
  "tool_instance_id": "hr-prod-01",
  "trigger_event": "employee.onboarding",
  "tool_context": {
    "employee_id": "EMP-5001",
    "start_date": "2024-02-20",
    "department": "Engineering",
    "role": "Software Engineer",
    "location": "San Francisco",
    "device_preferences": {
      "type": "laptop",
      "model": "MacBook Pro 14-inch"
    },
    "target_agent_id": "device-provisioning-agent"
  },
  "metadata": {
    "onboarding_workflow": "engineering-new-hire",
    "priority": "high"
  }
}
```

## Integration Examples

### Python Integration

```python
import requests
import json
from datetime import datetime

class ToolIntegrationClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'x-api-key': self.api_key
        })
    
    def send_tool_request(self, user_id, content, tool_id, trigger_event, 
                         tool_context=None, metadata=None):
        """Send a tool integration request."""
        
        payload = {
            'user_id': user_id,
            'content': content,
            'tool_id': tool_id,
            'trigger_event': trigger_event,
            'tool_context': tool_context or {},
            'metadata': metadata or {}
        }
        
        response = self.session.post(
            f"{self.base_url}/api/v1/requests/tool",
            json=payload
        )
        
        response.raise_for_status()
        return response.json()

# Usage example
client = ToolIntegrationClient(
    base_url="http://request-manager.<NAMESPACE>.svc.cluster.local",
    api_key="your-api-key"
)

# Laptop refresh notification
response = client.send_tool_request(
    user_id="alice.johnson",
    content="Laptop refresh due based on asset age policy",
    tool_id="snow-integration",
    trigger_event="asset.refresh.due",
    tool_context={
        "asset_tag": "LAPTOP-12345",
        "current_model": "Dell Latitude 7420",
        "purchase_date": "2021-01-15",
        "target_agent_id": "laptop-refresh-agent"
    },
    metadata={
        "automation_rule": "3-year-refresh-policy",
        "correlation_id": f"refresh-{datetime.now().isoformat()}"
    }
)

print(f"Request sent: {response['request_id']}")
```

### Bash/Shell Integration

```bash
#!/bin/bash

# Configuration
BASE_URL="http://request-manager.<NAMESPACE>.svc.cluster.local"
API_KEY="your-api-key"
TOOL_ID="monitoring-system"

# Function to send tool request
send_tool_request() {
    local user_id="$1"
    local content="$2"
    local trigger_event="$3"
    local tool_context="$4"
    
    curl -X POST \
        -H "Content-Type: application/json" \
        -H "x-api-key: $API_KEY" \
        "$BASE_URL/api/v1/requests/tool" \
        -d "{
            \"user_id\": \"$user_id\",
            \"content\": \"$content\",
            \"tool_id\": \"$TOOL_ID\",
            \"trigger_event\": \"$trigger_event\",
            \"tool_context\": $tool_context
        }"
}

# Example: Performance alert
send_tool_request \
    "bob.smith" \
    "Performance degradation detected on user's device" \
    "performance.degradation" \
    '{
        "device_id": "LAPTOP-67890",
        "performance_score": 2.1,
        "threshold": 3.0,
        "target_agent_id": "performance-troubleshooting-agent"
    }'
```

### ServiceNow Integration

```javascript
// ServiceNow Business Rule or Scheduled Job
(function() {
    // Get devices due for refresh
    var grDevices = new GlideRecord('cmdb_ci_computer');
    grDevices.addQuery('sys_updated_on', '<=', 'javascript:gs.daysAgo(1095)'); // 3 years
    grDevices.query();
    
    while (grDevices.next()) {
        var user = grDevices.assigned_to;
        if (user) {
            // Call tool integration endpoint
            var request = new sn_ws.RESTMessageV2();
            request.setEndpoint('http://request-manager.<NAMESPACE>.svc.cluster.local/api/v1/requests/tool');
            request.setHttpMethod('POST');
            request.setRequestHeader('Content-Type', 'application/json');
            request.setRequestHeader('x-api-key', 'your-api-key');
            
            var payload = {
                user_id: user.getDisplayValue(),
                content: 'Automated notification: Laptop refresh due based on asset age policy',
                tool_id: 'snow-integration',
                trigger_event: 'asset.refresh.due',
                tool_context: {
                    asset_tag: grDevices.asset_tag.toString(),
                    current_model: grDevices.model_number.toString(),
                    purchase_date: grDevices.sys_created_on.toString(),
                    target_agent_id: 'laptop-refresh-agent'
                }
            };
            
            request.setRequestBody(JSON.stringify(payload));
            var response = request.execute();
        }
    }
})();
```

## Agent Routing

### Direct Agent Routing

Tools can specify a target agent to bypass general routing:

```json
{
  "tool_context": {
    "target_agent_id": "laptop-refresh-agent"
  }
}
```

### Built-in Tool-to-Agent Mapping

The system includes predefined mappings:

| Tool ID | Default Agent |
|---------|---------------|
| `snow-integration` | `laptop-refresh-agent` |
| `email-service` | `email-change-agent` |
| `performance-monitor` | `performance-troubleshooting-agent` |
| `security-scanner` | `security-remediation-agent` |

### Custom Routing Logic

Tools can implement custom routing based on:
- Trigger event type
- User department/role
- Device type
- Priority level
- Compliance requirements

## Response Handling

### Success Response

```json
{
  "status": "success",
  "request_id": "req_abc123",
  "session_id": "sess_def456",
  "message": "Request processed successfully",
  "agent_response": {
    "agent_id": "laptop-refresh-agent",
    "estimated_completion": "2024-02-15T10:00:00Z",
    "next_steps": ["User notification", "Device assessment", "Refresh scheduling"]
  }
}
```

### Error Responses

#### Authentication Error (401)
```json
{
  "status": "error",
  "error": "Invalid API key",
  "details": "API key validation failed for tool_id: your-tool-id"
}
```

#### Validation Error (400)
```json
{
  "status": "error",
  "error": "Validation failed",
  "details": {
    "field": "tool_id",
    "message": "tool_id is required and cannot be empty"
  }
}
```

## Best Practices

### 1. Content Guidelines

- **Be Descriptive**: Provide clear, actionable content that explains the issue
- **Include Context**: Reference specific systems, policies, or timeframes
- **Use Business Language**: Write for the end user, not technical systems

**Good Example**:
```
"Automated notification: User's laptop is due for refresh based on asset management policy. Current device is 3+ years old and may impact productivity."
```

**Poor Example**:
```
"LAPTOP_REFRESH_DUE_ALERT"
```

### 2. Tool Context Structure

- **Use Consistent Keys**: Standardize field names across your tool integrations
- **Include Relevant Data**: Provide all information the agent might need
- **Avoid Sensitive Data**: Don't include passwords or personal information

### 3. Metadata Usage

- **Correlation IDs**: Use unique identifiers to track related requests
- **Automation Rules**: Reference the policy or rule that triggered the request
- **Timestamps**: Include when the event occurred, not when the request was sent

### 4. Error Handling

```python
try:
    response = client.send_tool_request(...)
    if response['status'] == 'success':
        logger.info(f"Tool request successful: {response['request_id']}")
    else:
        logger.error(f"Tool request failed: {response['error']}")
except requests.exceptions.RequestException as e:
    logger.error(f"Network error: {e}")
    # Implement retry logic
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

### 5. Rate Limiting

- **Respect Limits**: Don't overwhelm the system with rapid requests
- **Batch Operations**: Group related requests when possible
- **Implement Backoff**: Use exponential backoff for retries

## Troubleshooting

### Common Issues

#### 1. Authentication Failures

**Problem**: `401 Unauthorized` response

**Solutions**:
- Verify API key is correct
- Ensure `tool_id` matches the registered tool
- Check that API key header is properly formatted

#### 2. Validation Errors

**Problem**: `400 Bad Request` with validation details

**Solutions**:
- Ensure all required fields are present
- Check field types match the schema
- Validate string length limits

#### 3. Agent Routing Issues

**Problem**: Request not reaching intended agent

**Solutions**:
- Verify `target_agent_id` is correct
- Check tool-to-agent mapping configuration
- Ensure agent is active and available

#### 4. Network Connectivity

**Problem**: Connection timeouts or network errors

**Solutions**:
- Verify base URL is correct and accessible
- Check network connectivity from tool environment
- Implement retry logic with exponential backoff

### Debugging Tools

#### Health Check
```bash
curl http://request-manager.<NAMESPACE>.svc.cluster.local/health
```

#### Request Logging
Enable detailed logging in your tool to track:
- Request payloads
- Response codes
- Error messages
- Timing information

## Security Considerations

### API Key Management

- **Rotate Keys**: Regularly rotate API keys for security
- **Scope Access**: Limit API keys to specific tools and functions
- **Monitor Usage**: Track API key usage for anomalies

### Data Protection

- **Encrypt Sensitive Data**: Use encryption for sensitive information in transit
- **Minimize Data**: Only include necessary information in requests
- **Audit Trails**: Maintain logs of all tool interactions

### Network Security

- **Use HTTPS**: Ensure all communications use secure protocols
- **Network Isolation**: Limit network access to necessary endpoints
- **Firewall Rules**: Configure appropriate firewall rules

## Support and Resources

### Documentation
- [Integration Guide](INTEGRATION_GUIDE.md) - Complete integration and request management guide
- [API Reference](../docs/API_REFERENCE.md) - Complete API documentation and endpoints
- [Architecture Diagrams](../docs/ARCHITECTURE_DIAGRAMS.md) - System architecture and flow diagrams
