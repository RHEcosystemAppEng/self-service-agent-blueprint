#!/bin/bash

# Simple script to list Slack users in the integration system
# Usage: ./scripts/list-slack-users.sh [user_id] [base_url]

set -e

USER_ID=$1
BASE_URL=${2:-"http://localhost:8080"}

if [ -n "$USER_ID" ]; then
    # List integrations for specific user
    echo "Fetching integrations for user: $USER_ID"
    echo "Base URL: $BASE_URL"
    echo ""
    
    response=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/v1/users/$USER_ID/integrations")
    
    # Parse response (portable way)
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ]; then
        echo "✅ User integrations:"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    else
        echo "❌ Failed to fetch user integrations. HTTP Code: $http_code"
        echo "Response: $body"
        exit 1
    fi
else
    # List all users would require a different endpoint or database query
    echo "Usage: $0 <user_id> [base_url]"
    echo ""
    echo "Examples:"
    echo "  $0 john.doe                                        # List integrations for john.doe"
    echo "  $0 jane.smith http://localhost:8081                # List integrations using custom URL"
    echo "  $0 bob.wilson https://integration-dispatcher.com   # List integrations using HTTPS"
    echo ""
    echo "To add a new user:"
    echo "  ./scripts/add-slack-user.sh <user_id> <email>"
fi
