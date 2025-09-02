#!/bin/bash

# Simple script to remove a Slack user from the integration system
# Usage: ./scripts/remove-slack-user.sh <user_id> [base_url]

set -e

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <user_id> [base_url]"
    echo ""
    echo "Examples:"
    echo "  $0 john.doe"
    echo "  $0 jane.smith http://localhost:8081"
    echo "  $0 bob.wilson https://integration-dispatcher.example.com"
    echo ""
    echo "Note: Make sure integration-dispatcher is accessible (kubectl port-forward if needed)"
    exit 1
fi

USER_ID=$1
BASE_URL=${2:-"http://localhost:8080"}

echo "Removing Slack integration for user..."
echo "  User ID: $USER_ID"
echo "  Base URL: $BASE_URL"
echo ""

# Confirm deletion
echo "⚠️  Warning: This will also delete all delivery logs for this user's Slack integration."
read -p "Are you sure you want to remove Slack integration for user '$USER_ID'? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "❌ Operation cancelled"
    exit 0
fi

# Delete the integration config
response=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL/api/v1/users/$USER_ID/integrations/SLACK")

# Parse response (portable way)
http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 204 ]; then
    echo "✅ Success! Slack integration removed for user: $USER_ID"
    echo ""
    echo "Response details:"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
elif [ "$http_code" -eq 404 ]; then
    echo "⚠️  No Slack integration found for user: $USER_ID"
    echo "The user may not have had Slack integration configured."
else
    echo "❌ Failed to remove user integration. HTTP Code: $http_code"
    echo "Response: $body"
    exit 1
fi

echo ""
echo "🎯 Next steps:"
echo "1. User '$USER_ID' will no longer receive Slack notifications"
echo "2. Verify removal: ./scripts/list-slack-users.sh $USER_ID"
echo "3. Re-add if needed: ./scripts/add-slack-user.sh $USER_ID <email>"
