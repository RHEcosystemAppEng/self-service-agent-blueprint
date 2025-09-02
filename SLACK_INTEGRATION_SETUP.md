# Slack Integration Setup Guide

This guide explains how to set up and configure Slack integration using the **Integration Defaults** system.

## 🎯 **Overview**

The Slack integration is managed through the **Integration Defaults** system, which provides:
- **Automatic configuration** based on system health checks
- **Smart defaults** for all users
- **User-specific overrides** when needed
- **Two-way interaction** with the AI agent

## 🔧 **Integration Defaults for Slack**

### **Default Configuration**
```json
{
  "enabled": true,  // Auto-enabled if Slack is configured
  "priority": 1,    // Highest priority (delivered first)
  "retry_count": 3,
  "retry_delay_seconds": 60,
  "config": {
    "thread_replies": false,
    "mention_user": false,
    "include_agent_info": true
  }
}
```

### **How It Works**
1. **System checks** if Slack is properly configured
2. **Auto-enables** Slack integration if health check passes
3. **All users** get Slack integration by default
4. **Users can override** with custom configurations if needed

## 🚀 **Quick Setup**

### **Step 1: Configure Slack App**

1. **Go to [Slack API Apps](https://api.slack.com/apps)**
2. **Click "Create New App"**
3. **Choose "From an app manifest"**
4. **Select your workspace**
5. **Copy and paste the contents of `slack-app-manifest.json`** from this repository
6. **Click "Next" → "Create"**

The manifest is available in [`slack-app-manifest.json`](../slack-app-manifest.json).

**Note**: Replace `YOUR_INTEGRATION_DISPATCHER_ROUTE` with your actual Integration Dispatcher route URL.

### **Step 2: Get Integration Dispatcher Route**

```bash
kubectl get route -n ${NAMESPACE:-default} | grep integration-dispatcher
```

The URL will be something like:
`https://self-service-agent-integration-dispatcher-${NAMESPACE:-default}.${DOMAIN:-apps.your-domain.com}`

### **Step 3: Configure Request URLs**

After creating the app, update the placeholder URLs:

1. **Go to "Event Subscriptions"**
2. **Update Request URL** to: `https://your-integration-dispatcher-route/slack/events`
3. **Click "Save Changes"**

4. **Go to "Interactivity & Shortcuts"** 
5. **Update Request URL** to: `https://your-integration-dispatcher-route/slack/interactive`
6. **Click "Save Changes"**

### **Step 4: Install App to Workspace**

1. **Go to "Install App"**
2. **Click "Install to Workspace"**
3. **Authorize the app**

### **Step 5: Get Bot Token and Signing Secret**

1. **Copy the Bot User OAuth Token** (starts with `xoxb-`)
2. **Go to "Basic Information"**
3. **Copy the Signing Secret**

### **Step 6: Deploy with Slack Configuration**

The Helm chart will automatically create the secrets when you provide the Slack credentials via environment variables:

**Option 1: Set credentials as environment variables**
```bash
# Set your Slack credentials as environment variables
export SLACK_BOT_TOKEN="xoxb-your-actual-bot-token"
export SLACK_SIGNING_SECRET="your-actual-signing-secret"

# Deploy with Slack integration enabled
make helm-install-dev NAMESPACE=your-namespace
```

**Option 2: Enable Slack and let Makefile prompt for credentials**
```bash
# Enable Slack integration and let Makefile prompt for credentials
ENABLE_SLACK=true make helm-install-dev NAMESPACE=your-namespace
```

**Option 3: Set all credentials via environment variables**
```bash
# Set all required environment variables
export ENABLE_SLACK=true
export SLACK_BOT_TOKEN="xoxb-your-actual-bot-token"
export SLACK_SIGNING_SECRET="your-actual-signing-secret"

# Deploy with Slack integration enabled
make helm-install-dev NAMESPACE=your-namespace
```

### **Step 7: Restart Integration Dispatcher**

```bash
kubectl rollout restart deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}
```

### **Step 8: Verify Configuration**

```bash
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} | grep -i slack
```

## 🔍 **Check Integration Status**

### **Check System Defaults**
```bash
curl http://localhost:8080/api/v1/integration-defaults
```

Look for `"SLACK"` in the response with `"enabled": true`.

### **Check Health Endpoint**
```bash
curl http://localhost:8080/health
```

Look for `"SLACK"` in the `integrations_available` array.

## 👤 **User Configuration**

### **Default Behavior**
- **All users** automatically get Slack integration when enabled
- **No configuration needed** for basic functionality when enabled
- **Uses system defaults** for delivery behavior

### **Custom User Configuration (Optional)**

If you need to customize Slack behavior for specific users:

```bash
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "john.doe@company.com",
      "thread_replies": true,
      "mention_user": true,
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
| `user_email` | string | User's email address for Slack user lookup |
| `thread_replies` | boolean | Reply in thread instead of new message |
| `mention_user` | boolean | Mention user in responses |
| `include_agent_info` | boolean | Include agent information in responses |

## 🔄 **Two-Way Interaction**

Users can interact with the AI agent in multiple ways:

### **1. Direct Messages**
Send a DM to the bot for private conversations.

### **2. Slash Commands**
Use `/agent [your message]` in any channel.

### **3. @Mentions**
Mention the bot in channels: `@Self-Service Agent help me`

### **4. Interactive Buttons**
Click buttons in agent responses for quick actions.

## 🧪 **Testing the Integration**

### **Test Basic Functionality**
```bash
# Send a test request
curl -X POST http://localhost:8080/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer web-test-user" \
  -d '{
    "integration_type": "slack",
    "user_id": "U09EPAXGNLS",
    "content": "Test message from integration"
  }'
```

### **Test User Configuration**
```bash
# Check user's effective configuration
curl http://localhost:8080/api/v1/users/U09EPAXGNLS/integration-defaults
```

### **Monitor Delivery**
```bash
# Watch Integration Dispatcher logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}

# Look for successful delivery
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} | grep -i "delivered to slack"
```

## 🔧 **Advanced Configuration**

### **Environment Variables**

You can override Slack defaults using environment variables:

```bash
# Override enabled status (overrides health check)
INTEGRATION_DEFAULTS_SLACK_ENABLED=true

# Override priority
INTEGRATION_DEFAULTS_SLACK_PRIORITY=1

# Override retry settings
INTEGRATION_DEFAULTS_SLACK_RETRY_COUNT=5
INTEGRATION_DEFAULTS_SLACK_RETRY_DELAY_SECONDS=30
```

### **Custom Slack Configuration**

For advanced use cases, you can create custom Slack configurations:

```bash
curl -X POST http://localhost:8080/api/v1/users/manager/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "manager@company.com",
      "thread_replies": true,
      "mention_user": true,
      "include_agent_info": true,
      "channel_id": "C1234567890"
    },
    "priority": 1,
    "retry_count": 5,
    "retry_delay_seconds": 30
  }'
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Slack integration not working**
   - Check if Slack is enabled in defaults: `GET /api/v1/integration-defaults`
   - Verify bot token and signing secret are configured
   - Check Integration Dispatcher logs for errors

2. **User not receiving messages**
   - Check user's effective configuration: `GET /api/v1/users/{user_id}/integration-defaults`
   - Verify user has Slack integration enabled
   - Check delivery logs: `GET /api/v1/users/{user_id}/deliveries`

3. **App not responding to events**
   - Verify request URLs are correct in Slack app settings
   - Check that Integration Dispatcher is accessible
   - Verify signing secret matches

### **Debug Commands**

```bash
# Check integration health
curl http://localhost:8080/health

# Check Slack-specific health
curl http://localhost:8080/health | jq '.integrations_available'

# Check user delivery history
curl http://localhost:8080/api/v1/users/U09EPAXGNLS/deliveries

# Reset user to defaults
curl -X POST http://localhost:8080/api/v1/users/U09EPAXGNLS/integration-defaults/reset
```

## 📚 **Best Practices**

1. **Use Integration Defaults** - Let the system handle most users automatically
2. **Test After Setup** - Verify the integration works end-to-end
3. **Monitor Delivery Logs** - Check for failed deliveries
4. **Configure Retry Settings** - Based on your Slack app reliability
5. **Use Descriptive User IDs** - For easier management
6. **Keep Configurations Simple** - Only override when necessary

## 🎯 **Summary**

The Slack integration uses the **Integration Defaults** system to provide:
- **Automatic configuration** for all users
- **Smart fallback behavior** when users have no custom config
- **Easy customization** when needed
- **Consistent delivery** across the system

Most users will get Slack integration automatically without any configuration needed!