#!/bin/bash

# Simple script to add a Slack user to the integration system
# Usage: ./scripts/add-slack-user.sh <user_id> <email> [workspace_id] [base_url]

set -e

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <user_id> <email> [workspace_id] [base_url]"
    echo ""
    echo "Examples:"
    echo "  $0 john.doe john.doe@company.com"
    echo "  $0 jane.smith jane.smith@company.com T1234567890"
    echo "  $0 bob.wilson bob.wilson@company.com T1234567890 http://localhost:8081"
    echo "  $0 alice.cooper alice.cooper@company.com T1234567890 https://integration-dispatcher.example.com"
    echo ""
    echo "Note: Make sure integration-dispatcher is accessible (kubectl port-forward if needed)"
    exit 1
fi

USER_ID=$1
EMAIL=$2
WORKSPACE_ID=${3:-"T1234567890"}
BASE_URL=${4:-"http://localhost:8080"}

echo "Adding Slack user configuration..."
echo "  User ID: $USER_ID"
echo "  Email: $EMAIL"
echo "  Workspace ID: $WORKSPACE_ID"
echo "  Base URL: $BASE_URL"
echo ""

# Create the integration config
response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/users/$USER_ID/integrations" \
  -H 'Content-Type: application/json' \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "'"$EMAIL"'",
      "workspace_id": "'"$WORKSPACE_ID"'",
      "thread_replies": false,
      "mention_user": false,
      "include_agent_info": true
    },
    "priority": 1,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }')

# Parse response (portable way)
http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
    echo "✅ Success! Slack integration configured for user: $USER_ID"
    echo ""
    echo "Configuration details:"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo "❌ Failed to add user. HTTP Code: $http_code"
    echo "Response: $body"
    exit 1
fi

echo ""
echo "🎯 Next steps:"
echo "1. User '$USER_ID' can now receive Slack notifications"
echo "2. Test with: make test-generic-request USER_ID=$USER_ID"
echo "3. View user configs: curl $BASE_URL/api/v1/users/$USER_ID/integrations"
