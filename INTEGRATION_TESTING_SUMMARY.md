# Integration Testing Summary

## 🎯 Quick Start Guide

### **1. Test Integration (Console Logging) - Easiest**
```bash
# Set your environment
export NAMESPACE=your-namespace
export DOMAIN=apps.your-domain.com

# Run the test
./scripts/test-integrations.sh
```

### **2. Email Integration Testing**
```bash
# Set up email credentials
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export TEST_EMAIL=test@example.com

# Run email test
./scripts/test-email-integration.sh
```

### **3. Webhook Integration Testing**
```bash
# Start webhook test server
./scripts/webhook-test-server.py

# In another terminal, run integration test with webhook
export WEBHOOK_URL=http://localhost:8080/
./scripts/test-integrations.sh
```

## 📋 Available Integrations

| Integration | Type | Status | Testing Method |
|-------------|------|--------|----------------|
| **Slack** | `SLACK` | ✅ Working | Use existing Slack setup |
| **Email** | `EMAIL` | ✅ Ready | SMTP configuration required |
| **Webhook** | `WEBHOOK` | ✅ Ready | HTTP endpoint required |
| **Test** | `TEST` | ✅ Ready | Console logging (no config needed) |

## 🛠️ Testing Tools Created

### **1. Main Integration Test Script**
- **File**: `scripts/test-integrations.sh`
- **Purpose**: Test all integrations with one command
- **Features**: 
  - Creates test user configurations
  - Sends test notifications
  - Monitors delivery logs
  - Supports all integration types

### **2. Email Integration Test Script**
- **File**: `scripts/test-email-integration.sh`
- **Purpose**: Dedicated email integration testing
- **Features**:
  - SMTP connectivity testing
  - Email delivery verification
  - Gmail/Office 365 support
  - Delivery log checking

### **3. Webhook Test Server**
- **File**: `scripts/webhook-test-server.py`
- **Purpose**: Local webhook endpoint for testing
- **Features**:
  - Web interface to view received webhooks
  - Real-time webhook monitoring
  - JSON data display
  - Auto-refresh functionality

## 🚀 Testing Workflows

### **Workflow 1: Quick Test (Test Integration)**
```bash
# 1. Run basic test
./scripts/test-integrations.sh

# 2. Monitor logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE} | grep "TEST INTEGRATION DELIVERY"
```

### **Workflow 2: Email Integration Test**
```bash
# 1. Set up email credentials
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export TEST_EMAIL=test@example.com

# 2. Test SMTP connectivity
./scripts/test-email-integration.sh test-smtp

# 3. Run full email test
./scripts/test-email-integration.sh

# 4. Check your email inbox
```

### **Workflow 3: Webhook Integration Test**
```bash
# 1. Start webhook test server
./scripts/webhook-test-server.py

# 2. Set webhook URL
export WEBHOOK_URL=http://localhost:8080/

# 3. Run integration test
./scripts/test-integrations.sh

# 4. View webhooks in browser at http://localhost:8080
```

### **Workflow 4: End-to-End Testing**
```bash
# 1. Set up all integrations
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export TEST_EMAIL=test@example.com
export WEBHOOK_URL=http://localhost:8080/

# 2. Start webhook server
./scripts/webhook-test-server.py &

# 3. Run comprehensive test
./scripts/test-integrations.sh

# 4. Verify all deliveries
# - Check email inbox
# - Check webhook server interface
# - Check console logs for test integration
```

## 🔧 Configuration Examples

### **Gmail SMTP Configuration**
```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password  # Use App Password, not regular password
export SMTP_USE_TLS=true
export FROM_EMAIL=noreply@yourdomain.com
export FROM_NAME="Self-Service Agent"
```

### **Office 365 SMTP Configuration**
```bash
export SMTP_HOST=smtp.office365.com
export SMTP_PORT=587
export SMTP_USERNAME=your-email@company.com
export SMTP_PASSWORD=your-password
export SMTP_USE_TLS=true
export FROM_EMAIL=noreply@yourdomain.com
export FROM_NAME="Self-Service Agent"
```

### **Webhook Configuration**
```bash
# For local testing
export WEBHOOK_URL=http://localhost:8080/

# For webhook.site testing
export WEBHOOK_URL=https://webhook.site/your-unique-url

# For custom webhook endpoint
export WEBHOOK_URL=https://your-webhook-endpoint.com/webhook
```

## 📊 Verification Methods

### **1. Console Logs (Test Integration)**
```bash
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE} | grep "TEST INTEGRATION DELIVERY"
```

### **2. Email Delivery**
- Check your email inbox
- Look for test message with subject "Integration Test - [timestamp]"

### **3. Webhook Delivery**
- Check webhook test server interface
- Look for POST requests with test data

### **4. API Verification**
```bash
# Check delivery logs
curl -s "${INTEGRATION_DISPATCHER_URL}/api/v1/delivery-logs?user_id=${USER_ID}"

# Check user integrations
curl -s "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations"

# Check health status
curl -s "${INTEGRATION_DISPATCHER_URL}/health"
```

## 🐛 Troubleshooting

### **Common Issues**

#### **Email Integration Issues**
- **Problem**: SMTP authentication fails
- **Solution**: Use App Password for Gmail, check credentials
- **Debug**: Run `./scripts/test-email-integration.sh test-smtp`

#### **Webhook Integration Issues**
- **Problem**: Webhook not receiving data
- **Solution**: Check URL accessibility, verify SSL certificates
- **Debug**: Use webhook test server for local testing

#### **Test Integration Issues**
- **Problem**: No console logs
- **Solution**: Check Integration Dispatcher logs, verify user configuration
- **Debug**: Monitor logs with `kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE}`

### **Debug Commands**
```bash
# Check Integration Dispatcher health
curl -s "${INTEGRATION_DISPATCHER_URL}/health"

# Check database connectivity
kubectl exec -n ${NAMESPACE} pgvector-0 -- psql -U postgres -d rag_blueprint -c "SELECT * FROM user_integration_configs LIMIT 5;"

# Check delivery logs
curl -s "${INTEGRATION_DISPATCHER_URL}/api/v1/delivery-logs" | jq '.'

# Monitor real-time logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE}
```

## 📈 Next Steps

1. **Run basic tests** to verify system functionality
2. **Configure email integration** for production use
3. **Set up webhook endpoints** for external systems
4. **Monitor delivery logs** for production monitoring
5. **Set up alerting** for failed deliveries
6. **Test error scenarios** and retry logic
7. **Performance test** under load

## 🎉 Success Criteria

- ✅ **Test Integration**: Console logs show delivery messages
- ✅ **Email Integration**: Test emails received in inbox
- ✅ **Webhook Integration**: Webhook endpoint receives test data
- ✅ **Health Checks**: All integrations show as available
- ✅ **Delivery Logs**: Successful delivery status recorded
- ✅ **Error Handling**: Failed deliveries are retried appropriately

**All integrations are now ready for testing and production use!** 🚀
