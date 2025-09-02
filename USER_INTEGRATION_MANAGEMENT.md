# User Integration Management Guide

This guide explains how the Self-Service Agent system manages user integrations using **Integration Defaults** and **User Overrides**.

## 🎯 **Overview**

The system uses a **two-tier configuration approach**:

1. **Integration Defaults** - System-wide default configurations for all integrations
2. **User Overrides** - Custom configurations that override defaults for specific users

### **How It Works**

```
User Request → Check User Overrides → Fall back to Integration Defaults → Deliver
```

- If a user has **custom configurations**, those are used
- If a user has **no custom configurations**, system defaults are used (lazy approach)
- Users can have **partial overrides** (e.g., only EMAIL configured, others use defaults)

### **Lazy Integration Approach**

The system uses a **lazy approach** for integration defaults:

- **No database entries** are created for users who don't need custom overrides
- **Smart defaults** are applied dynamically without persistence
- **User configs** are only created when users explicitly override defaults
- **Better performance** - fewer database queries and no constraint violations

## 🔧 **Integration Defaults**

Integration defaults are **system-wide configurations** that provide smart fallback behavior for all users.

### **Supported Integration Types**

| Integration | Default Priority | Default Retry | Status |
|-------------|------------------|---------------|--------|
| **SLACK** | 1 (highest) | 3 retries, 60s delay | ✅ Auto-enabled if configured |
| **EMAIL** | 2 | 3 retries, 60s delay | ✅ Auto-enabled if configured |
| **WEBHOOK** | 3 | 1 retry, 30s delay | ❌ Always disabled by default |
| **SMS** | 4 | 2 retries, 45s delay | ❌ Always disabled by default |
| **TEST** | 5 | 1 retry, 10s delay | ✅ Auto-enabled if configured |
| **CLI** | 6 | 1 retry, 5s delay | ✅ Auto-enabled if configured |
| **TOOL** | 7 (lowest) | 1 retry, 5s delay | ✅ Auto-enabled if configured |

### **Default Configuration Examples**

#### **SLACK Defaults**
```json
{
  "enabled": true,  // Auto-enabled if Slack is configured
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

#### **EMAIL Defaults**
```json
{
  "enabled": true,  // Auto-enabled if SMTP is configured
  "priority": 2,
  "retry_count": 3,
  "retry_delay_seconds": 60,
  "config": {
    "include_agent_info": true
  }
}
```

## 📋 **API Endpoints**

### **Base URL**
- **Local Development**: `http://localhost:8080` (with port-forward)
- **Production**: `https://your-integration-dispatcher-url`

### **Available Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/integration-defaults` | Get system integration defaults |
| `GET` | `/api/v1/users/{user_id}/integration-defaults` | Get user's effective configuration |
| `POST` | `/api/v1/users/{user_id}/integration-defaults/reset` | Reset user to defaults |
| `GET` | `/api/v1/users/{user_id}/integrations` | List user's custom configurations |
| `POST` | `/api/v1/users/{user_id}/integrations` | Create user override |
| `PUT` | `/api/v1/users/{user_id}/integrations/{integration_type}` | Update user override |
| `DELETE` | `/api/v1/users/{user_id}/integrations/{integration_type}` | Delete user override |
| `GET` | `/api/v1/users/{user_id}/deliveries` | Get user delivery history |

## 🚀 **Quick Start**

### **1. Check System Defaults**
```bash
curl http://localhost:8080/api/v1/integration-defaults
```

### **2. Check User's Effective Configuration**
```bash
curl http://localhost:8080/api/v1/users/john.doe/integration-defaults
```

This shows:
- User's custom overrides (if any)
- Effective configuration (defaults + overrides)
- Whether user is using integration defaults

### **3. Create User Override (Optional)**
```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "john.doe@company.com",
      "format": "html"
    },
    "priority": 1,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

## 🔧 **Integration Defaults Management**

### **Get System Integration Defaults**
```bash
curl http://localhost:8080/api/v1/integration-defaults
```

**Response:**
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

### **Get User's Effective Configuration**
```bash
curl http://localhost:8080/api/v1/users/john.doe/integration-defaults
```

**Response (User with custom EMAIL configuration):**
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

**Response (User with no custom configurations):**
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

### **Reset User to Integration Defaults**
```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integration-defaults/reset
```

This removes all custom user configurations and falls back to system defaults.

## 👤 **User Override Management**

### **Create User Override**
```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "john.doe@company.com",
      "thread_replies": true,
      "mention_user": true
    },
    "priority": 1,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

### **Update User Override**
```bash
curl -X PUT http://localhost:8080/api/v1/users/john.doe/integrations/SLACK \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": false,
    "retry_count": 10
  }'
```

### **Delete User Override**
```bash
curl -X DELETE http://localhost:8080/api/v1/users/john.doe/integrations/SLACK
```

### **List User Overrides**
```bash
curl http://localhost:8080/api/v1/users/john.doe/integrations
```

## 📊 **Delivery History and Monitoring**

### **Get User Delivery History**
```bash
# Get recent deliveries (default: 50 records)
curl http://localhost:8080/api/v1/users/john.doe/deliveries

# Get specific number of records with pagination
curl "http://localhost:8080/api/v1/users/john.doe/deliveries?limit=20&offset=0"
```

### **Delivery Log Parameters**
- `limit`: Number of records to return (default: 50)
- `offset`: Number of records to skip for pagination (default: 0)

### **Delivery Log Response**
Each delivery log includes:
- `delivery_id`: Unique delivery identifier
- `user_id`: User who received the delivery
- `integration_type`: Type of integration used
- `status`: Delivery status (success, failed, pending)
- `created_at`: When the delivery was attempted
- `error_message`: Error details if delivery failed

## 🎯 **Best Practices**

1. **Use Integration Defaults** - Let the system handle most users automatically
2. **Override Only When Needed** - Create user overrides for special cases
3. **Monitor Delivery Logs** - Check for failed deliveries and troubleshoot
4. **Set Appropriate Priorities** - Higher priority = delivered first
5. **Configure Retry Settings** - Based on integration reliability
6. **Test After Changes** - Verify integrations work after configuration
7. **Use Descriptive User IDs** - For easier management and debugging

## 🔍 **Troubleshooting**

### **Check Integration Health**
```bash
curl http://localhost:8080/health
```

### **View Delivery Logs**
```bash
curl http://localhost:8080/api/v1/users/john.doe/deliveries
```

### **Reset User to Defaults**
```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integration-defaults/reset
```

### **Common Issues**

1. **User not receiving notifications**
   - Check if user has overrides: `GET /api/v1/users/{user_id}/integration-defaults`
   - Check delivery logs: `GET /api/v1/users/{user_id}/deliveries`
   - Verify integration health: `GET /health`

2. **Integration not working**
   - Check system defaults: `GET /api/v1/integration-defaults`
   - Verify integration is enabled in defaults
   - Check if user has disabled override

3. **Wrong priority order**
   - Check effective configuration: `GET /api/v1/users/{user_id}/integration-defaults`
   - Adjust user override priority if needed
   - Reset to defaults if configuration is wrong

## 📚 **Advanced Configuration**

### **Environment Variables for Defaults**

You can override system defaults using environment variables:

```bash
# Override enabled status (overrides health check for health-checkable integrations)
INTEGRATION_DEFAULTS_SLACK_ENABLED=true
INTEGRATION_DEFAULTS_EMAIL_ENABLED=true
INTEGRATION_DEFAULTS_CLI_ENABLED=true
INTEGRATION_DEFAULTS_TOOL_ENABLED=true

# Override priority
INTEGRATION_DEFAULTS_SLACK_PRIORITY=1
INTEGRATION_DEFAULTS_EMAIL_PRIORITY=2

# Override retry settings
INTEGRATION_DEFAULTS_SLACK_RETRY_COUNT=5
INTEGRATION_DEFAULTS_SLACK_RETRY_DELAY_SECONDS=30
INTEGRATION_DEFAULTS_EMAIL_RETRY_COUNT=3
INTEGRATION_DEFAULTS_EMAIL_RETRY_DELAY_SECONDS=60
```

### **Integration-Specific Configuration**

Each integration type has specific configuration options:

#### **SLACK Configuration**
```json
{
  "user_email": "user@company.com",
  "thread_replies": true,
  "mention_user": true,
  "include_agent_info": true
}
```

#### **EMAIL Configuration**
```json
{
  "email_address": "user@company.com",
  "format": "html",
  "include_agent_info": true
}
```

#### **WEBHOOK Configuration**
```json
{
  "url": "https://webhook.site/your-url",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer your-token"
  }
}
```

This approach provides a **flexible, maintainable system** where most users get sensible defaults automatically, while power users can customize their experience as needed.