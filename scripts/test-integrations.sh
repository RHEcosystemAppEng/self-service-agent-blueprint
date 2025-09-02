#!/bin/bash

# Integration Testing Script
# This script helps test all integrations (Email, Webhook, Test) in the Self-Service Agent system

set -e

# Configuration
NAMESPACE=${NAMESPACE:-default}
DOMAIN=${DOMAIN:-apps.your-domain.com}
USER_ID="test-user-$(date +%s)"

# URLs
INTEGRATION_DISPATCHER_URL="https://self-service-agent-integration-dispatcher-${NAMESPACE}.${DOMAIN}"
REQUEST_MANAGER_URL="https://self-service-agent-request-manager-${NAMESPACE}.${DOMAIN}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if required tools are installed
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is required but not installed"
        exit 1
    fi
    
    log_success "All dependencies are available"
}

# Check if services are accessible
check_services() {
    log_info "Checking service accessibility..."
    
    # Check Integration Dispatcher
    if curl -s -f "${INTEGRATION_DISPATCHER_URL}/health" > /dev/null; then
        log_success "Integration Dispatcher is accessible"
    else
        log_error "Integration Dispatcher is not accessible at ${INTEGRATION_DISPATCHER_URL}"
        exit 1
    fi
    
    # Check Request Manager
    if curl -s -f "${REQUEST_MANAGER_URL}/health" > /dev/null; then
        log_success "Request Manager is accessible"
    else
        log_error "Request Manager is not accessible at ${REQUEST_MANAGER_URL}"
        exit 1
    fi
}

# Test Integration Dispatcher health
test_health() {
    log_info "Testing Integration Dispatcher health..."
    
    response=$(curl -s "${INTEGRATION_DISPATCHER_URL}/health")
    echo "Health response: $response"
    
    if echo "$response" | grep -q '"status":"healthy"'; then
        log_success "Integration Dispatcher is healthy"
    else
        log_warning "Integration Dispatcher health check returned unexpected status"
    fi
}

# Create test user integration configuration
create_test_integrations() {
    log_info "Creating test integration configurations for user: $USER_ID"
    
    # Test Integration (Console Logging)
    log_info "Creating TEST integration..."
    curl -s -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
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
            "priority": 1,
            "retry_count": 1,
            "retry_delay_seconds": 30
        }' > /dev/null
    
    log_success "TEST integration created"
    
    # Email Integration (if SMTP is configured)
    if [[ -n "${SMTP_HOST:-}" ]]; then
        log_info "Creating EMAIL integration..."
        curl -s -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
            -H "Content-Type: application/json" \
            -d '{
                "integration_type": "EMAIL",
                "enabled": true,
                "config": {
                    "email_address": "'${TEST_EMAIL:-test@example.com}'",
                    "display_name": "Test User",
                    "format": "html",
                    "include_signature": true,
                    "include_agent_info": true
                },
                "priority": 2,
                "retry_count": 3,
                "retry_delay_seconds": 60
            }' > /dev/null
        
        log_success "EMAIL integration created"
    else
        log_warning "SMTP_HOST not set, skipping EMAIL integration test"
    fi
    
    # Webhook Integration (if webhook URL is provided)
    if [[ -n "${WEBHOOK_URL:-}" ]]; then
        log_info "Creating WEBHOOK integration..."
        curl -s -X POST "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" \
            -H "Content-Type: application/json" \
            -d '{
                "integration_type": "WEBHOOK",
                "enabled": true,
                "config": {
                    "url": "'${WEBHOOK_URL}'",
                    "method": "POST",
                    "headers": {
                        "X-Custom-Header": "test-value"
                    },
                    "timeout_seconds": 30,
                    "verify_ssl": true
                },
                "priority": 3,
                "retry_count": 3,
                "retry_delay_seconds": 60
            }' > /dev/null
        
        log_success "WEBHOOK integration created"
    else
        log_warning "WEBHOOK_URL not set, skipping WEBHOOK integration test"
    fi
}

# List user integrations
list_integrations() {
    log_info "Listing integrations for user: $USER_ID"
    
    response=$(curl -s "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations")
    echo "User integrations: $response"
}

# Send test notification
send_test_notification() {
    log_info "Sending test notification..."
    
    response=$(curl -s -X POST "${INTEGRATION_DISPATCHER_URL}/notifications" \
        -H "Content-Type: application/json" \
        -d '{
            "request_id": "test-request-'$(date +%s)'",
            "session_id": "test-session-'$(date +%s)'",
            "user_id": "'${USER_ID}'",
            "agent_id": "test-agent",
            "subject": "Integration Test - '$(date)'",
            "body": "This is a test message to verify integration delivery works correctly.\n\nTest details:\n- User ID: '${USER_ID}'\n- Timestamp: '$(date)'\n- Test ID: integration-test-001",
            "template_variables": {
                "user_name": "Test User",
                "agent_name": "Test Agent",
                "timestamp": "'$(date)'"
            }
        }')
    
    echo "Notification response: $response"
    log_success "Test notification sent"
}

# Monitor Integration Dispatcher logs
monitor_logs() {
    log_info "Monitoring Integration Dispatcher logs for test delivery..."
    log_info "Press Ctrl+C to stop monitoring"
    
    kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE} | grep -E "(TEST INTEGRATION DELIVERY|delivery|integration)"
}

# Clean up test data
cleanup() {
    log_info "Cleaning up test data..."
    
    # Delete user integrations
    curl -s -X DELETE "${INTEGRATION_DISPATCHER_URL}/api/v1/users/${USER_ID}/integrations" > /dev/null || true
    
    log_success "Cleanup completed"
}

# Main function
main() {
    echo "🧪 Integration Testing Script"
    echo "=============================="
    echo "Namespace: $NAMESPACE"
    echo "Domain: $DOMAIN"
    echo "User ID: $USER_ID"
    echo "Integration Dispatcher: $INTEGRATION_DISPATCHER_URL"
    echo "Request Manager: $REQUEST_MANAGER_URL"
    echo ""
    
    check_dependencies
    check_services
    test_health
    
    echo ""
    log_info "Starting integration tests..."
    
    create_test_integrations
    list_integrations
    
    echo ""
    log_info "Sending test notification in 3 seconds..."
    sleep 3
    send_test_notification
    
    echo ""
    log_info "Test completed! Check the logs for delivery confirmation:"
    echo "kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE} | grep 'TEST INTEGRATION DELIVERY'"
    
    echo ""
    log_info "To monitor logs in real-time, run:"
    echo "kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE}"
}

# Handle script arguments
case "${1:-}" in
    "monitor")
        monitor_logs
        ;;
    "cleanup")
        cleanup
        ;;
    "health")
        test_health
        ;;
    "list")
        list_integrations
        ;;
    "send")
        send_test_notification
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  (no args)  Run full integration test"
        echo "  monitor    Monitor Integration Dispatcher logs"
        echo "  cleanup    Clean up test data"
        echo "  health     Test Integration Dispatcher health"
        echo "  list       List user integrations"
        echo "  send       Send test notification"
        echo "  help       Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  NAMESPACE     Kubernetes namespace (default: default)"
        echo "  DOMAIN        OpenShift cluster domain"
        echo "  SMTP_HOST     SMTP server for email testing"
        echo "  TEST_EMAIL    Email address for testing"
        echo "  WEBHOOK_URL   Webhook URL for testing"
        echo ""
        echo "Examples:"
        echo "  # Basic test"
        echo "  $0"
        echo ""
        echo "  # Test with email integration"
        echo "  SMTP_HOST=smtp.gmail.com TEST_EMAIL=test@example.com $0"
        echo ""
        echo "  # Test with webhook integration"
        echo "  WEBHOOK_URL=https://webhook.site/your-unique-url $0"
        echo ""
        echo "  # Monitor logs"
        echo "  $0 monitor"
        ;;
    *)
        main
        ;;
esac
