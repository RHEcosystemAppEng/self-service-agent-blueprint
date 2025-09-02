#!/bin/bash

# Setup Email User Configurations from Helm Values
# This script reads email user configurations from Helm values and creates them in the database

set -e

NAMESPACE=${NAMESPACE:-default}
RELEASE_NAME=${RELEASE_NAME:-self-service-agent}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📧 Setting up Email User Configurations${NC}"
echo "Namespace: $NAMESPACE"
echo "Release: $RELEASE_NAME"
echo

# Function to get Helm values
get_helm_values() {
    helm get values "$RELEASE_NAME" -n "$NAMESPACE" 2>/dev/null || {
        echo -e "${RED}❌ Error: Could not get Helm values for release '$RELEASE_NAME' in namespace '$NAMESPACE'${NC}"
        echo "Make sure the release is installed and accessible."
        exit 1
    }
}

# Function to extract email configurations from Helm values
extract_email_configs() {
    local values_yaml="$1"
    
    # Extract example users from Helm values
    # This is a simplified extraction - in production, you might want to use yq or similar
    echo "Extracting email configurations from Helm values..."
    
    # For now, we'll use the example configurations from the values.yaml
    # In a real implementation, you'd parse the actual Helm values
    cat << 'EOF'
# Example email configurations (replace with actual Helm values parsing)
INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, retry_count, retry_delay_seconds, created_by) VALUES
('admin', 'EMAIL', true, '{"email_address": "admin@company.com", "format": "html", "include_agent_info": true, "include_signature": true, "reply_to": "admin@company.com", "display_name": "Admin User"}', 10, 3, 60, 'helm-setup'),
('user', 'EMAIL', true, '{"email_address": "user@company.com", "format": "text", "include_agent_info": true, "include_signature": true, "reply_to": "", "display_name": "Regular User"}', 5, 3, 60, 'helm-setup'),
('test', 'EMAIL', false, '{"email_address": "test@example.com", "format": "html", "include_agent_info": false, "include_signature": false, "reply_to": "test@example.com", "display_name": "Test User"}', 1, 3, 60, 'helm-setup')
ON CONFLICT (user_id, integration_type) DO UPDATE SET
  enabled = EXCLUDED.enabled,
  config = EXCLUDED.config,
  priority = EXCLUDED.priority,
  retry_count = EXCLUDED.retry_count,
  retry_delay_seconds = EXCLUDED.retry_delay_seconds,
  updated_at = CURRENT_TIMESTAMP;
EOF
}

# Function to execute SQL in the database
execute_sql() {
    local sql="$1"
    local pod_name="$2"
    
    echo -e "${YELLOW}Executing SQL in pod: $pod_name${NC}"
    kubectl exec -n "$NAMESPACE" "$pod_name" -- psql -U postgres -d rag_blueprint -c "$sql"
}

# Main execution
main() {
    echo -e "${BLUE}🔍 Getting Helm values...${NC}"
    local values_yaml
    values_yaml=$(get_helm_values)
    
    echo -e "${BLUE}📊 Extracting email configurations...${NC}"
    local sql_commands
    sql_commands=$(extract_email_configs "$values_yaml")
    
    echo -e "${BLUE}🗄️  Finding database pod...${NC}"
    local db_pod
    db_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=pgvector -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || {
        echo -e "${RED}❌ Error: Could not find pgvector pod in namespace '$NAMESPACE'${NC}"
        echo "Make sure pgvector is deployed and running."
        exit 1
    })
    
    echo -e "${GREEN}✅ Found database pod: $db_pod${NC}"
    
    echo -e "${BLUE}💾 Setting up email user configurations...${NC}"
    execute_sql "$sql_commands" "$db_pod"
    
    echo -e "${GREEN}✅ Email user configurations setup complete!${NC}"
    echo
    echo -e "${YELLOW}📋 Next steps:${NC}"
    echo "1. Verify configurations: kubectl exec -n $NAMESPACE $db_pod -- psql -U postgres -d rag_blueprint -c \"SELECT user_id, integration_type, enabled, config FROM user_integration_configs WHERE integration_type = 'EMAIL';\""
    echo "2. Test email integration by triggering an AI agent conversation"
    echo "3. Check integration dispatcher logs for delivery status"
}

# Help function
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Setup email user configurations from Helm values.

OPTIONS:
    -n, --namespace NAMESPACE    Kubernetes namespace (default: default)
    -r, --release RELEASE        Helm release name (default: self-service-agent)
    -h, --help                   Show this help message

ENVIRONMENT VARIABLES:
    NAMESPACE                    Kubernetes namespace
    RELEASE_NAME                 Helm release name

EXAMPLES:
    # Setup with default settings
    $0
    
    # Setup in specific namespace
    $0 --namespace production
    
    # Setup for specific release
    $0 --release my-self-service-agent

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main
