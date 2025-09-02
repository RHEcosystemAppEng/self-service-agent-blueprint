#!/bin/bash

# Universal script to add user integrations to the system
# Usage: ./scripts/add-user-integration.sh <integration_type> <user_id> <config_json> [base_url]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 3 ]; then
    echo -e "${BLUE}Usage: $0 <integration_type> <user_id> <config_json> [base_url]${NC}"
    echo ""
    echo -e "${YELLOW}Integration Types:${NC}"
    echo "  EMAIL    - Email notifications (✅ Implemented)"
    echo "  SLACK    - Slack notifications (✅ Implemented)" 
    echo "  WEBHOOK  - Webhook delivery (✅ Implemented)"
    echo "  TEST     - Test integration (✅ Implemented)"
    echo "  SMS      - SMS notifications (❌ Not Implemented)"
    echo "  TEAMS    - Microsoft Teams notifications (❌ Not Implemented)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo ""
    echo -e "${GREEN}# Email Integration:${NC}"
    echo "  $0 EMAIL john.doe '{\"email_address\": \"john.doe@company.com\", \"format\": \"html\", \"include_agent_info\": true}'"
    echo ""
    echo -e "${GREEN}# Slack Integration:${NC}"
    echo "  $0 SLACK jane.smith '{\"user_email\": \"jane.smith@company.com\", \"workspace_id\": \"T1234567890\", \"thread_replies\": false}'"
    echo ""
    echo -e "${GREEN}# Webhook Integration:${NC}"
    echo "  $0 WEBHOOK system.monitor '{\"url\": \"https://webhook.site/your-url\", \"method\": \"POST\", \"headers\": {\"X-Custom\": \"value\"}}'"
    echo ""
    echo -e "${GREEN}# With custom base URL:${NC}"
    echo "  $0 EMAIL bob.wilson '{\"email_address\": \"bob@company.com\"}' https://your-api.com"
    echo ""
    echo -e "${YELLOW}Note: Make sure integration-dispatcher is accessible (kubectl port-forward if needed)${NC}"
    exit 1
fi

INTEGRATION_TYPE=$1
USER_ID=$2
CONFIG_JSON=$3
BASE_URL=${4:-"https://self-service-agent-integration-dispatcher-tommy.apps.ai-dev02.kni.syseng.devcluster.openshift.com"}

# Validate integration type
case "$INTEGRATION_TYPE" in
    EMAIL|SLACK|WEBHOOK|TEST)
        ;;
    SMS|TEAMS)
        echo -e "${RED}❌ Error: Integration type '$INTEGRATION_TYPE' is not yet implemented${NC}"
        echo "Currently implemented: EMAIL, SLACK, WEBHOOK, TEST"
        echo "SMS and TEAMS are planned but not yet available"
        exit 1
        ;;
    *)
        echo -e "${RED}❌ Error: Invalid integration type '$INTEGRATION_TYPE'${NC}"
        echo "Valid types: EMAIL, SLACK, WEBHOOK, TEST"
        echo "Planned types: SMS, TEAMS (not yet implemented)"
        exit 1
        ;;
esac

echo -e "${BLUE}🔧 Adding $INTEGRATION_TYPE integration for user: $USER_ID${NC}"
echo "  User ID: $USER_ID"
echo "  Integration Type: $INTEGRATION_TYPE"
echo "  Base URL: $BASE_URL"
echo "  Config: $CONFIG_JSON"
echo ""

# Create the integration config
response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/users/$USER_ID/integrations" \
  -H 'Content-Type: application/json' \
  -d '{
    "integration_type": "'"$INTEGRATION_TYPE"'",
    "enabled": true,
    "config": '"$CONFIG_JSON"',
    "priority": 5,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }')

# Parse response (portable way)
http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
    echo -e "${GREEN}✅ Success! $INTEGRATION_TYPE integration configured for user: $USER_ID${NC}"
    echo ""
    echo -e "${BLUE}Configuration details:${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${RED}❌ Failed to add user integration. HTTP Code: $http_code${NC}"
    echo "Response: $body"
    exit 1
fi

echo ""
echo -e "${YELLOW}🎯 Next steps:${NC}"
echo "1. User '$USER_ID' can now receive $INTEGRATION_TYPE notifications"
echo "2. Test with: curl -X POST $BASE_URL/api/v1/requests/generic -H 'Content-Type: application/json' -d '{\"user_id\": \"$USER_ID\", \"content\": \"Test message\", \"integration_type\": \"$INTEGRATION_TYPE\"}'"
echo "3. View user configs: curl $BASE_URL/api/v1/users/$USER_ID/integrations"
echo "4. Update config: curl -X PUT $BASE_URL/api/v1/users/$USER_ID/integrations/$INTEGRATION_TYPE -H 'Content-Type: application/json' -d '{\"enabled\": true, \"config\": {...}}'"
