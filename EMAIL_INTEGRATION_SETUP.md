# Email Integration Setup Guide

This guide explains how to set up and configure email integration using the **Integration Defaults** system.

## 🎯 **Overview**

The email integration is managed through the **Integration Defaults** system, which provides:
- **Automatic configuration** based on system health checks
- **Smart defaults** for all users
- **User-specific overrides** when needed
- **HTML and text email support** with configurable templates

## 🔧 **Integration Defaults for Email**

### **Default Configuration**
```json
{
  "enabled": true,  // Auto-enabled if SMTP is configured
  "priority": 2,    // Second priority (after Slack)
  "retry_count": 3,
  "retry_delay_seconds": 60,
  "config": {
    "include_agent_info": true
  }
}
```

### **How It Works**
1. **System checks** if SMTP is properly configured
2. **Auto-enables** email integration if health check passes
3. **All users** get email integration by default
4. **Users can override** with custom configurations if needed

## 🚀 **Quick Setup**

### **Step 1: Configure SMTP Server**

Configure your SMTP server settings in the Helm values:

```yaml
security:
  email:
    # SMTP Server Configuration
    smtpHost: "smtp.gmail.com"          # Your SMTP server
    smtpPort: "587"                     # Port (587 for STARTTLS, 465 for SSL)
    smtpUsername: "your-email@gmail.com" # SMTP username
    smtpPassword: "your-app-password"   # SMTP password/app password
    smtpUseTls: "true"                  # Use TLS encryption
    fromEmail: "noreply@yourcompany.com" # From email address
    fromName: "Self-Service Agent"      # From name
```

### **Step 2: Deploy with Email Configuration**

```bash
make helm-install-dev \
  NAMESPACE=my-namespace \
  EXTRA_HELM_ARGS="--set security.email.smtpHost=smtp.gmail.com --set security.email.smtpPort=587 --set security.email.smtpUsername=your-email@gmail.com --set security.email.smtpPassword=your-app-password --set security.email.smtpUseTls=true --set security.email.fromEmail=noreply@yourcompany.com --set security.email.fromName='Self-Service Agent'"
```

### **Step 3: Verify Configuration**

```bash
# Check if email integration is enabled
curl http://localhost:8080/api/v1/integration-defaults

# Check health endpoint
curl http://localhost:8080/health
```

Look for `"EMAIL"` in the response with `"enabled": true`.

## 🔍 **Check Integration Status**

### **Check System Defaults**
```bash
curl http://localhost:8080/api/v1/integration-defaults
```

Look for `"EMAIL"` in the response with `"enabled": true`.

### **Check Health Endpoint**
```bash
curl http://localhost:8080/health
```

Look for `"EMAIL"` in the `integrations_available` array.

### **Test SMTP Connection**
```bash
kubectl exec -n your-namespace deployment/self-service-agent-integration-dispatcher -- python3 -c "
import smtplib
from email.mime.text import MIMEText
import os

smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
smtp_port = int(os.getenv('SMTP_PORT', '587'))
smtp_username = os.getenv('SMTP_USERNAME')
smtp_password = os.getenv('SMTP_PASSWORD')

try:
    server = smtplib.SMTP(smtp_host, smtp_port)
    server.starttls()
    server.login(smtp_username, smtp_password)
    print('SMTP connection successful')
    server.quit()
except Exception as e:
    print(f'SMTP connection failed: {e}')
"
```

## 👤 **User Configuration**

### **Default Behavior**
- **All users** automatically get email integration when enabled
- **No configuration needed** for basic functionality when enabled
- **Uses system defaults** for delivery behavior

### **Custom User Configuration (Optional)**

If you need to customize email behavior for specific users:

```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "john.doe@company.com",
      "format": "html",
      "include_agent_info": true
    },
    "priority": 1,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

### **Configuration Options**

| Field | Type | Description |
|-------|------|-------------|
| `email_address` | string | User's email address |
| `format` | string | Email format: "html" or "text" (default: "html") |
| `include_agent_info` | boolean | Include agent information in responses |

## 🧪 **Testing the Integration**

### **Test Basic Functionality**
```bash
# Send a test request
curl -X POST http://localhost:8080/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer web-test-user" \
  -d '{
    "integration_type": "email",
    "user_id": "john.doe",
    "content": "Test message from integration"
  }'
```

### **Test User Configuration**
```bash
# Check user's effective configuration
curl http://localhost:8080/api/v1/users/john.doe/integration-defaults
```

### **Monitor Delivery**
```bash
# Watch Integration Dispatcher logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n your-namespace

# Look for successful delivery
kubectl logs deployment/self-service-agent-integration-dispatcher -n your-namespace | grep -i "delivered to email"
```

## 🔧 **Advanced Configuration**

### **Environment Variables**

You can override email defaults using environment variables:

```bash
# Override enabled status (overrides health check)
INTEGRATION_DEFAULTS_EMAIL_ENABLED=true

# Override priority
INTEGRATION_DEFAULTS_EMAIL_PRIORITY=2

# Override retry settings
INTEGRATION_DEFAULTS_EMAIL_RETRY_COUNT=5
INTEGRATION_DEFAULTS_EMAIL_RETRY_DELAY_SECONDS=30
```

### **Custom Email Configuration**

For advanced use cases, you can create custom email configurations:

```bash
curl -X POST http://localhost:8080/api/v1/users/manager/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "manager@company.com",
      "format": "html",
      "include_agent_info": true
    },
    "priority": 1,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

## 📧 **Email Templates and Formatting**

### **HTML Email Format**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Self-Service Agent Response</title>
</head>
<body>
    <h2>AI Agent Response</h2>
    <p>Your request has been processed:</p>
    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px;">
        {{content}}
    </div>
    <p><small>Sent by Self-Service Agent</small></p>
</body>
</html>
```

### **Plain Text Format**
```
AI Agent Response

Your request has been processed:

{{content}}

---
Sent by Self-Service Agent
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Email integration not working**
   - Check if email is enabled in defaults: `GET /api/v1/integration-defaults`
   - Verify SMTP configuration is correct
   - Check Integration Dispatcher logs for errors

2. **User not receiving emails**
   - Check user's effective configuration: `GET /api/v1/users/{user_id}/integration-defaults`
   - Verify user has email integration enabled
   - Check delivery logs: `GET /api/v1/users/{user_id}/deliveries`

3. **SMTP authentication failed**
   - Verify SMTP credentials are correct
   - Check if app passwords are required (Gmail, etc.)
   - Ensure TLS/SSL settings are correct

### **Debug Commands**

```bash
# Check integration health
curl http://localhost:8080/health

# Check email-specific health
curl http://localhost:8080/health | jq '.integrations_available'

# Check user delivery history
curl http://localhost:8080/api/v1/users/john.doe/deliveries

# Reset user to defaults
curl -X POST http://localhost:8080/api/v1/users/john.doe/integration-defaults/reset
```

### **SMTP Configuration Examples**

#### **Gmail Configuration**
```yaml
security:
  email:
    smtpHost: "smtp.gmail.com"
    smtpPort: "587"
    smtpUsername: "your-email@gmail.com"
    smtpPassword: "your-app-password"  # Use App Password, not regular password
    smtpUseTls: "true"
    fromEmail: "your-email@gmail.com"
    fromName: "Self-Service Agent"
```

#### **Outlook/Hotmail Configuration**
```yaml
security:
  email:
    smtpHost: "smtp-mail.outlook.com"
    smtpPort: "587"
    smtpUsername: "your-email@outlook.com"
    smtpPassword: "your-password"
    smtpUseTls: "true"
    fromEmail: "your-email@outlook.com"
    fromName: "Self-Service Agent"
```

#### **Custom SMTP Server**
```yaml
security:
  email:
    smtpHost: "mail.yourcompany.com"
    smtpPort: "587"
    smtpUsername: "noreply@yourcompany.com"
    smtpPassword: "your-password"
    smtpUseTls: "true"
    fromEmail: "noreply@yourcompany.com"
    fromName: "Self-Service Agent"
```

## 📚 **Best Practices**

1. **Use Integration Defaults** - Let the system handle most users automatically
2. **Test SMTP Connection** - Verify email delivery works end-to-end
3. **Monitor Delivery Logs** - Check for failed deliveries
4. **Configure Retry Settings** - Based on your SMTP server reliability
5. **Use App Passwords** - For Gmail and other services that require them
6. **Keep Configurations Simple** - Only override when necessary
7. **Use HTML Format** - For better user experience

## 🎯 **Summary**

The email integration uses the **Integration Defaults** system to provide:
- **Automatic configuration** for all users
- **Smart fallback behavior** when users have no custom config
- **Easy customization** when needed
- **Consistent delivery** across the system

Most users will get email integration automatically without any configuration needed!