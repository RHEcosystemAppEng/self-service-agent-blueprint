# User Integration Management Guide

This guide explains how to add, configure, and manage user integrations in the Self-Service Agent system.

## 🎯 **Overview**

The system supports multiple integration types for delivering AI agent responses to users:
- **EMAIL** - Email notifications ✅ **Fully Implemented**
- **SLACK** - Slack direct messages and channel notifications ✅ **Fully Implemented**
- **WEBHOOK** - HTTP webhook delivery to external systems ✅ **Fully Implemented**
- **TEST** - Test integration for development ✅ **Fully Implemented**
- **SMS** - SMS notifications ❌ **Schema Only (Not Implemented)**
- **TEAMS** - Microsoft Teams notifications ❌ **Schema Only (Not Implemented)**

### **Implementation Status**

| Integration | Status | Handler | Schema | Notes |
|-------------|--------|---------|--------|-------|
| EMAIL | ✅ **Fully Implemented** | ✅ | ✅ | SMTP support with HTML/text formatting |
| SLACK | ✅ **Fully Implemented** | ✅ | ✅ | Bot token + webhook support |
| WEBHOOK | ✅ **Fully Implemented** | ✅ | ✅ | HTTP delivery with auth support |
| TEST | ✅ **Fully Implemented** | ✅ | ✅ | Development/testing only |
| SMS | ❌ **Not Implemented** | ❌ | ✅ | Schema exists, handler missing |
| TEAMS | ❌ **Not Implemented** | ❌ | ❌ | Planned for future release |

**Note**: SMS and TEAMS integrations are defined in the database schema but do not have working handlers. Attempting to use them will result in delivery failures.

## 🔧 **Recommended Approach: Use API Endpoints**

**Always use the REST API endpoints** instead of direct database inserts. The API provides:
- ✅ Data validation and business logic
- ✅ Proper error handling and rollback
- ✅ Audit trail and consistency
- ✅ Future-proof compatibility

## 📋 **API Endpoints**

### **Base URL**
- **Local Development**: `http://localhost:8080` (with port-forward)
- **Production**: `https://your-integration-dispatcher-url`
- **OpenShift Routes**: Use the auto-generated routes for direct external access

#### **Finding Your Route URLs**
```bash
# Get available routes
kubectl get routes -n your-namespace

# Example output:
# NAME                                        HOST/PORT
# self-service-agent-integration-dispatcher   self-service-agent-integration-dispatcher-tommy.apps.ai-dev02.kni.syseng.devcluster.openshift.com
# self-service-agent-request-manager          self-service-agent-request-manager-tommy.apps.ai-dev02.kni.syseng.devcluster.openshift.com
```

#### **Using Routes Instead of Port-Forward**
```bash
# Instead of port-forwarding:
# kubectl port-forward svc/self-service-agent-integration-dispatcher 8080:80 -n your-namespace

# Use the route directly:
BASE_URL="https://self-service-agent-integration-dispatcher-tommy.apps.ai-dev02.kni.syseng.devcluster.openshift.com"
./scripts/add-user-integration.sh EMAIL john.doe '{"email_address": "john@company.com"}' "$BASE_URL"
```

### **Available Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/users/{user_id}/integrations` | Create user integration |
| `GET` | `/api/v1/users/{user_id}/integrations` | List user integrations |
| `PUT` | `/api/v1/users/{user_id}/integrations/{integration_type}` | Update user integration |
| `DELETE` | `/api/v1/users/{user_id}/integrations/{integration_type}` | Delete user integration |

## 🚀 **Quick Start: Universal Script**

Use the universal script for all integration types:

```bash
# Make script executable
chmod +x scripts/add-user-integration.sh

# Add email integration
./scripts/add-user-integration.sh EMAIL john.doe '{"email_address": "john.doe@company.com", "format": "html", "include_agent_info": true}'

# Add Slack integration
./scripts/add-user-integration.sh SLACK jane.smith '{"user_email": "jane.smith@company.com", "workspace_id": "T1234567890", "thread_replies": false}'

# Add webhook integration
./scripts/add-user-integration.sh WEBHOOK system.monitor '{"url": "https://webhook.site/your-url", "method": "POST", "headers": {"X-Custom": "value"}}'
```

## 🔄 **Multiple Integrations for Same User**

**Users can have multiple integration types configured simultaneously!** When a request comes in, the system will deliver to ALL configured integrations in parallel.

### **Example: User with Email + Slack + Webhook**

```bash
# Configure user "john.doe" with multiple integrations
./scripts/add-user-integration.sh EMAIL john.doe '{"email_address": "john.doe@company.com", "format": "html", "include_agent_info": true}'
./scripts/add-user-integration.sh SLACK john.doe '{"user_email": "john.doe@company.com", "workspace_id": "T1234567890", "thread_replies": false}'
./scripts/add-user-integration.sh WEBHOOK john.doe '{"url": "https://webhook.site/your-url", "method": "POST", "headers": {"X-Custom": "value"}}'

# View all integrations for the user
curl "https://your-integration-dispatcher-url/api/v1/users/john.doe/integrations"

# Trigger a request - will go to ALL configured integrations
curl -X POST "https://your-request-manager-url/api/v1/requests/generic" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "john.doe",
    "content": "This message will be sent to email, Slack, AND webhook!",
    "integration_type": "WEB"
  }'
```

### **How Multiple Integrations Work**

1. **Database Design**: Each user can have exactly one configuration per integration type (EMAIL, SLACK, WEBHOOK, etc.)
2. **Parallel Processing**: When a request comes in, the system retrieves ALL enabled integrations for the user
3. **Priority Ordering**: Integrations are processed in priority order (higher priority first)
4. **Independent Delivery**: Each integration is delivered independently - if one fails, others continue
5. **Status Tracking**: Delivery status is tracked separately for each integration

### **Priority and Retry Settings**

The script uses default priority (5) and retry settings. For custom priorities, use the API directly:

```bash
# High-priority user with multiple integrations (using API directly)
curl -X POST "https://your-integration-dispatcher-url/api/v1/users/manager/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {"email_address": "manager@company.com"},
    "priority": 10,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'

curl -X POST "https://your-integration-dispatcher-url/api/v1/users/manager/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {"user_email": "manager@company.com"},
    "priority": 8,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }'
```

## 📧 **Email Integration**

### **Configuration Fields**
```json
{
  "email_address": "user@company.com",     // Required: User's email address
  "format": "html",                        // Optional: "html" or "text" (default: "html")
  "include_agent_info": true,              // Optional: Include agent ID in email (default: true)
  "include_signature": true,               // Optional: Include system signature (default: true)
  "reply_to": "user@company.com",          // Optional: Reply-to address
  "display_name": "John Doe"               // Optional: Display name in email clients
}
```

### **Examples**

**Basic Email Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "john.doe@company.com",
      "format": "html",
      "include_agent_info": true,
      "include_signature": true
    }
  }'
```

**Advanced Email Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/admin/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "admin@company.com",
      "format": "html",
      "include_agent_info": true,
      "include_signature": true,
      "reply_to": "admin@company.com",
      "display_name": "Admin User"
    },
    "priority": 10,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

## 💬 **Slack Integration**

### **Configuration Fields**
```json
{
  "user_email": "user@company.com",        // Required: User's email address
  "workspace_id": "T1234567890",           // Optional: Slack workspace ID
  "thread_replies": false,                 // Optional: Use thread replies (default: false)
  "mention_user": false,                   // Optional: Mention user in messages (default: false)
  "include_agent_info": true,              // Optional: Include agent ID (default: true)
  "channel_id": "C1234567890"              // Optional: Specific channel for notifications
}
```

### **Examples**

**Basic Slack Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/jane.smith/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "jane.smith@company.com",
      "workspace_id": "T1234567890",
      "thread_replies": false,
      "mention_user": false
    }
  }'
```

**Advanced Slack Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/manager/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "manager@company.com",
      "workspace_id": "T1234567890",
      "thread_replies": true,
      "mention_user": true,
      "channel_id": "C1234567890",
      "include_agent_info": true
    },
    "priority": 8,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }'
```

## 🔗 **Webhook Integration**

### **Configuration Fields**
```json
{
  "url": "https://webhook.site/your-url",   // Required: Webhook URL
  "method": "POST",                         // Optional: HTTP method (default: "POST")
  "headers": {                              // Optional: Custom headers
    "Content-Type": "application/json",
    "X-Custom-Header": "value"
  },
  "timeout_seconds": 30,                    // Optional: Request timeout (default: 30)
  "verify_ssl": true,                       // Optional: Verify SSL certificates (default: true)
  "auth_type": "bearer",                    // Optional: "bearer", "api_key", "basic"
  "auth_config": {                          // Optional: Authentication configuration
    "token": "your-bearer-token"
  }
}
```

### **Examples**

**Basic Webhook Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/system.monitor/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "WEBHOOK",
    "enabled": true,
    "config": {
      "url": "https://webhook.site/your-unique-url",
      "method": "POST",
      "headers": {
        "Content-Type": "application/json",
        "X-Source": "Self-Service-Agent"
      }
    }
  }'
```

**Authenticated Webhook Setup:**
```bash
curl -X POST http://localhost:8080/api/v1/users/itsm.system/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "WEBHOOK",
    "enabled": true,
    "config": {
      "url": "https://your-itsm-system.com/api/incidents",
      "method": "POST",
      "headers": {
        "Content-Type": "application/json"
      },
      "auth_type": "bearer",
      "auth_config": {
        "token": "your-api-token"
      },
      "timeout_seconds": 60,
      "verify_ssl": true
    }
  }'
```

## 🔍 **Managing User Integrations**

### **List User Integrations**
```bash
curl http://localhost:8080/api/v1/users/john.doe/integrations
```

### **Update User Integration**
```bash
curl -X PUT http://localhost:8080/api/v1/users/john.doe/integrations/EMAIL \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": false,
    "config": {
      "email_address": "john.doe@newcompany.com",
      "format": "text"
    }
  }'
```

### **Delete User Integration**
```bash
curl -X DELETE http://localhost:8080/api/v1/users/john.doe/integrations/EMAIL
```

## 🧪 **Testing User Integrations**

### **Test Email Integration**
```bash
curl -X POST http://localhost:8080/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer web-test-user" \
  -d '{
    "user_id": "john.doe",
    "content": "This is a test email message",
    "client_ip": "192.168.1.1",
    "request_type": "test",
    "integration_type": "EMAIL"
  }'
```

### **Test Webhook Integration**
```bash
curl -X POST http://localhost:8080/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer web-test-user" \
  -d '{
    "user_id": "system.monitor",
    "content": "This is a test webhook message",
    "client_ip": "192.168.1.1",
    "request_type": "test",
    "integration_type": "WEBHOOK"
  }'
```

### **Check Delivery Status**
```bash
curl http://localhost:8080/api/v1/users/john.doe/deliveries
```

## 📊 **Integration Priority and Retry Settings**

### **Priority Levels**
- **10**: Critical (managers, admins)
- **5**: Normal (regular users)
- **1**: Low (test users, disabled by default)

### **Retry Configuration**
- **retry_count**: Number of delivery attempts (default: 3)
- **retry_delay_seconds**: Delay between retries (default: 60)

### **Example with Custom Settings**
```bash
curl -X POST http://localhost:8080/api/v1/users/ceo/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "ceo@company.com",
      "format": "html",
      "include_agent_info": true,
      "include_signature": true,
      "display_name": "CEO"
    },
    "priority": 10,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

## 🚨 **Common Issues and Solutions**

### **Port Forward Setup**
```bash
# For local testing
kubectl port-forward svc/self-service-agent-integration-dispatcher-00001-private 8080:80 -n your-namespace
```

### **Authentication Issues**
- Ensure you're using the correct base URL
- Check that the integration-dispatcher service is running
- Verify network connectivity

### **Configuration Validation**
- All required fields must be provided
- Email addresses must be valid format
- Webhook URLs must start with http:// or https://
- Integration types must be uppercase (EMAIL, SLACK, WEBHOOK, etc.)

## 📚 **Additional Resources**

- **API Documentation**: Check the OpenAPI spec at `/docs` endpoint
- **Health Checks**: Monitor integration health at `/health` endpoint
- **Delivery Logs**: View delivery history and status
- **Integration Testing**: Use the test scripts in the `scripts/` directory

## 🎯 **Best Practices**

1. **Use the API endpoints** instead of direct database access
2. **Test integrations** after configuration
3. **Set appropriate priorities** based on user importance
4. **Monitor delivery logs** for failed deliveries
5. **Use descriptive user IDs** for easier management
6. **Configure retry settings** based on integration reliability
7. **Keep configurations simple** - only set necessary fields
