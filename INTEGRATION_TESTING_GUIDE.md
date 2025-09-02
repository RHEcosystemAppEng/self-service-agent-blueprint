# Integration Testing Guide

## Overview

This guide covers how to properly test all integrations (Email, Webhooks, Tools) in the Self-Service Agent system. The system supports multiple delivery channels through the Integration Dispatcher.

## Available Integrations

### 1. **Slack Integration** ✅ (Already Working)
- **Type**: `SLACK`
- **Status**: Fully implemented and tested
- **Testing**: Use existing Slack setup

### 2. **Email Integration** 📧
- **Type**: `EMAIL`
- **Status**: Fully implemented
- **Features**: HTML/Text emails, SMTP delivery, custom headers

### 3. **Webhook Integration** 🔗
- **Type**: `WEBHOOK`
- **Status**: Fully implemented
- **Features**: HTTP POST/PUT, authentication, custom headers

### 4. **Test Integration** 🧪
- **Type**: `TEST`
- **Status**: Fully implemented
- **Features**: Console logging for testing

## Testing Setup

### Prerequisites

1. **Deploy the system** with Integration Dispatcher
2. **Set environment variables** for your testing environment
3. **Configure database** with user integration configs

### Environment Variables

```bash
# Set your testing environment
export NAMESPACE=${NAMESPACE:-default}
export DOMAIN=${DOMAIN:-apps.your-domain.com}

# Email configuration (for email integration testing)
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export SMTP_USE_TLS=true
export FROM_EMAIL=noreply@yourdomain.com
export FROM_NAME="Self-Service Agent"
```

## Testing Methods

### Method 1: Direct API Testing (Recommended)

#### 1. **Create User Integration Config**

```bash
# Set your integration dispatcher URL
INTEGRATION_DISPATCHER_URL="https://self-service-agent-integration-dispatcher-${NAMESPACE}.${DOMAIN}"

# Test user ID
USER_ID="test-user-123"
```

#### 2. **Test Email Integration**

```bash
# Create email integration config
curl -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "EMAIL",
    "enabled": true,
    "config": {
      "email_address": "test@example.com",
      "display_name": "Test User",
      "format": "html",
      "include_signature": true,
      "include_agent_info": true
    },
    "priority": 1,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }'
```

#### 3. **Test Webhook Integration**

```bash
# Create webhook integration config
curl -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "WEBHOOK",
    "enabled": true,
    "config": {
      "url": "https://webhook.site/your-unique-url",
      "method": "POST",
      "headers": {
        "X-Custom-Header": "test-value"
      },
      "timeout_seconds": 30,
      "verify_ssl": true,
      "auth_type": "bearer",
      "auth_config": {
        "token": "your-bearer-token"
      }
    },
    "priority": 2,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }'
```

#### 4. **Test Integration (Console Logging)**

```bash
# Create test integration config
curl -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "TEST",
    "enabled": true,
    "config": {
      "test_id": "test-001",
      "test_name": "E2E Test",
      "output_format": "json",
      "include_metadata": true
    },
    "priority": 3,
    "retry_count": 1,
    "retry_delay_seconds": 30
  }'
```

#### 5. **Trigger Test Delivery**

```bash
# Send a test notification
curl -X POST "${INTEGRATION_DISPATCHER_URL}/notifications" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-request-001",
    "session_id": "test-session-001",
    "user_id": "'${USER_ID}'",
    "agent_id": "test-agent",
    "subject": "Test Integration Delivery",
    "body": "This is a test message to verify integration delivery works correctly.",
    "template_variables": {
      "user_name": "Test User",
      "agent_name": "Test Agent"
    }
  }'
```

### Method 2: End-to-End Testing

#### 1. **Create Test User in Database**

```bash
# Insert test user configuration
kubectl exec -n ${NAMESPACE:-default} pgvector-0 -- psql -U postgres -d rag_blueprint -c "
INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, retry_count, retry_delay_seconds, created_at, updated_at)
VALUES (
  'test-user-123', 
  'EMAIL', 
  true, 
  '{
    \"email_address\": \"test@example.com\",
    \"display_name\": \"Test User\",
    \"format\": \"html\",
    \"include_signature\": true,
    \"include_agent_info\": true
  }'::jsonb,
  1,
  3,
  60,
  NOW(),
  NOW()
);
"
```

#### 2. **Send Request Through Request Manager**

```bash
# Set your request manager URL
REQUEST_MANAGER_URL="https://self-service-agent-request-manager-${NAMESPACE}.${DOMAIN}"

# Send a test request
curl -X POST "${REQUEST_MANAGER_URL}/api/v1/requests/generic/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "request_content": "Please help me test the email integration",
    "integration_type": "web"
  }'
```

## Testing Tools

### 1. **Webhook Testing with webhook.site**

1. Go to [webhook.site](https://webhook.site)
2. Copy your unique URL
3. Use it in webhook integration config
4. Send test requests and see real-time delivery

### 2. **Email Testing with Gmail**

1. Create a Gmail account for testing
2. Enable 2-factor authentication
3. Generate an app password
4. Use in SMTP configuration

### 3. **Console Testing with Test Integration**

The test integration logs all deliveries to the Integration Dispatcher console:

```bash
# Watch Integration Dispatcher logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}
```

Look for messages like:
```
🧪 TEST INTEGRATION DELIVERY: {
  "request_id": "test-request-001",
  "session_id": "test-session-001",
  "user_id": "test-user-123",
  "agent_id": "test-agent",
  "subject": "Test Integration Delivery",
  "content": "This is a test message...",
  "delivery_method": "TEST_INTEGRATION"
}
```

## Verification Steps

### 1. **Check Integration Health**

```bash
# Check Integration Dispatcher health
curl "${INTEGRATION_DISPATCHER_URL}/health"
```

Expected response:
```json
{
  "status": "healthy",
  "database_connected": true,
  "integrations_available": ["SLACK", "EMAIL", "WEBHOOK", "TEST"],
  "services": {
    "database": "connected",
    "integrations": "4/4 available"
  }
}
```

### 2. **Verify User Configurations**

```bash
# List user integrations
curl "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations"
```

### 3. **Check Delivery Logs**

```bash
# Check delivery logs
curl "${INTEGRATION_DISPATCHER_URL}/api/v1/delivery-logs?user_id=${USER_ID}"
```

## Troubleshooting

### Common Issues

#### 1. **Email Integration Fails**
- Check SMTP credentials
- Verify firewall/network access
- Check email provider settings

#### 2. **Webhook Integration Fails**
- Verify webhook URL is accessible
- Check authentication configuration
- Verify SSL certificates

#### 3. **Test Integration Not Logging**
- Check Integration Dispatcher logs
- Verify user configuration is enabled
- Check database connectivity

### Debug Commands

```bash
# Check Integration Dispatcher logs
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}

# Check database connectivity
kubectl exec -n ${NAMESPACE:-default} pgvector-0 -- psql -U postgres -d rag_blueprint -c "SELECT * FROM user_integration_configs WHERE user_id = 'test-user-123';"

# Test SMTP connectivity
kubectl exec -it deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} -- python -c "
import aiosmtplib
import asyncio
async def test():
    try:
        async with aiosmtplib.SMTP(hostname='smtp.gmail.com', port=587, use_tls=True) as smtp:
            print('SMTP connection successful')
    except Exception as e:
        print(f'SMTP connection failed: {e}')
asyncio.run(test())
"
```

## Test Scenarios

### 1. **Single Integration Test**
- Configure one integration type
- Send test request
- Verify delivery

### 2. **Multiple Integration Test**
- Configure multiple integration types for same user
- Send test request
- Verify delivery to all configured integrations

### 3. **Priority Testing**
- Configure integrations with different priorities
- Send test request
- Verify delivery order

### 4. **Retry Testing**
- Configure integration with retry settings
- Send request to failing endpoint
- Verify retry behavior

### 5. **Error Handling Test**
- Send request with invalid configuration
- Verify error handling and logging

## Production Readiness Checklist

- [ ] All integration types tested
- [ ] Error handling verified
- [ ] Retry logic tested
- [ ] Performance under load tested
- [ ] Security configurations verified
- [ ] Monitoring and alerting configured
- [ ] Documentation updated

## Next Steps

1. **Set up test environment** with proper credentials
2. **Run integration tests** using the methods above
3. **Verify all delivery channels** work correctly
4. **Test error scenarios** and retry logic
5. **Configure monitoring** for production use
