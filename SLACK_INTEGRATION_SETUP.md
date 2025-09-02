# Slack Integration Setup Guide

This guide walks you through setting up Slack integration for the Self-Service Agent system.

## Option 1: Quick Setup with App Manifest (Recommended)

### Step 1: Create Slack App from Manifest

1. **Go to [Slack API Apps](https://api.slack.com/apps)**
2. **Click "Create New App"**
3. **Choose "From an app manifest"**
4. **Select your workspace**
5. **Copy and paste the contents of `slack-app-manifest.json`** from this repository
6. **Click "Next" → "Create"**

The manifest will automatically configure:
- ✅ Required OAuth scopes for two-way interaction
- ✅ Bot user settings
- ✅ Event subscriptions for message handling
- ✅ Interactive components for button responses
- ✅ Slash command `/agent` for direct interaction

### Slack App Manifest Content

<details>
<summary>Click to view the complete JSON manifest</summary>

```json
{
  "display_information": {
    "name": "Self-Service Agent",
    "description": "AI-powered self-service agent that helps users with laptop refresh, email updates, and other IT requests",
    "background_color": "#2c3e50",
    "long_description": "The Self-Service Agent is an AI-powered assistant that helps employees with common IT requests like laptop refresh, email address updates, and other self-service tasks.\n\nFeatures:\n- Intelligent routing to appropriate agents\n- Real-time responses via Slack\n- Session-based conversations\n- Integration with existing IT workflows\n\nSimply send a request through your organization's request system and receive responses directly in Slack!"
  },
  "features": {
    "bot_user": {
      "display_name": "Self-Service Agent",
      "always_online": true
    },
    "app_home": {
      "home_tab_enabled": false,
      "messages_tab_enabled": true,
      "messages_tab_read_only_enabled": false
    },
    "slash_commands": [
      {
        "command": "/agent",
        "description": "Interact with the self-service agent",
        "usage_hint": "[your request or question]",
        "should_escape": false,
        "url": "https://YOUR_INTEGRATION_DISPATCHER_ROUTE/slack/commands"
      }
    ]
  },
  "oauth_config": {
    "scopes": {
      "bot": [
        "chat:write",
        "chat:write.public",
        "users:read",
        "users:read.email",
        "im:write",
        "im:read",
        "im:history",
        "channels:read",
        "channels:history",
        "groups:read",
        "app_mentions:read",
        "commands"
      ]
    }
  },
  "settings": {
    "event_subscriptions": {
      "request_url": "https://YOUR_INTEGRATION_DISPATCHER_ROUTE/slack/events",
      "bot_events": [
        "message.im",
        "app_mention",
        "message.channels"
      ]
    },
    "interactivity": {
      "is_enabled": true,
      "request_url": "https://YOUR_INTEGRATION_DISPATCHER_ROUTE/slack/interactive"
    },
    "org_deploy_enabled": false,
    "socket_mode_enabled": false,
    "token_rotation_enabled": false
  }
}
```

**Note**: Replace `YOUR_INTEGRATION_DISPATCHER_ROUTE` with your actual Integration Dispatcher route URL.

**Why JSON format?**
- ✅ **Better compatibility**: Avoids YAML parsing issues in Slack's interface
- ✅ **Easier validation**: JSON syntax errors are clearer
- ✅ **Standard format**: JSON is more universally supported

</details>

### Step 2: Get Integration Dispatcher Route

First, get your Integration Dispatcher route URL:

```bash
kubectl get route -n ${NAMESPACE:-default} | grep integration-dispatcher
```

The URL will be something like:
`https://self-service-agent-integration-dispatcher-${NAMESPACE:-default}.${DOMAIN:-apps.your-domain.com}`

### Step 3: Configure Request URLs

After creating the app, you need to update the placeholder URLs with your actual route:

1. **Go to "Event Subscriptions"**
2. **Update Request URL** to: `https://your-integration-dispatcher-route/slack/events`
3. **Click "Save Changes"**

4. **Go to "Interactivity & Shortcuts"** 
5. **Update Request URL** to: `https://your-integration-dispatcher-route/slack/interactive`
6. **Click "Save Changes"**

7. **Go to "Slash Commands"**
8. **Edit the `/agent` command**
9. **Update Request URL** to: `https://your-integration-dispatcher-route/slack/commands`
10. **Click "Save"**

### Step 4: Install and Get Tokens

1. **Go to "OAuth & Permissions"**
2. **Click "Install to Workspace"**
3. **Authorize the app**
4. **Copy the "Bot User OAuth Token"** (starts with `xoxb-`)
5. **Go to "Basic Information" → "App Credentials"**
6. **Copy the "Signing Secret"**

## Option 2: Manual Setup

If you prefer manual setup, follow these steps:

### Step 1: Create Slack App
1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name: "Self-Service Agent"
4. Select your workspace

### Step 2: Configure OAuth Scopes
Go to "OAuth & Permissions" and add these **Bot Token Scopes**:
- `chat:write` - Send messages
- `chat:write.public` - Send messages to channels the app isn't in
- `users:read` - View basic user info
- `users:read.email` - Look up users by email
- `conversations:read` - View basic channel info
- `conversations:history` - View message history
- `im:read` - View DM info
- `im:write` - Send DMs
- `im:history` - View DM history
- `channels:read` - View public channel info
- `groups:read` - View private channel info
- `mpim:read` - View group DM info

### Step 3: Configure Bot User
1. Go to "App Home"
2. Enable "Always Show My Bot as Online"
3. Set Display Name: "Self-Service Agent"

## Kubernetes Configuration

### Step 1: Create Integration Secrets

Replace `YOUR_BOT_TOKEN` and `YOUR_SIGNING_SECRET` with your actual values:

```bash
kubectl create secret generic self-service-agent-integration-secrets \
  --from-literal=slack-bot-token="xoxb-your-actual-bot-token" \
  --from-literal=slack-signing-secret="your-actual-signing-secret" \
  -n ${NAMESPACE:-default}
```

### Step 2: Restart Integration Dispatcher

```bash
kubectl rollout restart deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}
```

### Step 3: Verify Secret is Loaded

```bash
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} | grep -i slack
```

## User Configuration

### Configure Slack Integration for Users

There are several ways to add users to receive Slack notifications:

#### Method 1: Simple Script (Recommended)

Use the provided helper script:

```bash
# Add a single user
./scripts/add-slack-user.sh john.doe john.doe@company.com

# Add a user with custom workspace ID
./scripts/add-slack-user.sh jane.smith jane.smith@company.com T1234567890

# Add a user with custom URL (for port-forwarding or HTTPS)
./scripts/add-slack-user.sh bob.wilson bob.wilson@company.com T1234567890 http://localhost:8081
./scripts/add-slack-user.sh alice.cooper alice.cooper@company.com T1234567890 https://integration-dispatcher.example.com

# List a user's integrations
./scripts/list-slack-users.sh john.doe
./scripts/list-slack-users.sh jane.smith https://integration-dispatcher.example.com

# Remove a user's Slack integration
./scripts/remove-slack-user.sh john.doe
./scripts/remove-slack-user.sh jane.smith https://integration-dispatcher.example.com
```

#### Method 2: Makefile Targets

```bash
# Add a user using make
make add-slack-user USER=john.doe EMAIL=john.doe@company.com

# Add with custom workspace ID
make add-slack-user USER=jane.smith EMAIL=jane.smith@company.com WORKSPACE_ID=T1234567890

# Add with custom URL (HTTP or HTTPS)
make add-slack-user USER=bob.wilson EMAIL=bob.wilson@company.com URL=http://localhost:8081
make add-slack-user USER=alice.cooper EMAIL=alice.cooper@company.com URL=https://integration-dispatcher.example.com

# List user's integrations
make list-slack-user USER=john.doe
make list-slack-user USER=jane.smith URL=https://integration-dispatcher.example.com

# Remove a user's Slack integration
make remove-slack-user USER=john.doe
make remove-slack-user USER=jane.smith URL=https://integration-dispatcher.example.com
```

#### Method 3: REST API (Advanced)

Use the Integration Dispatcher API directly:

```bash
# Add a user
curl -X POST http://localhost:8080/api/v1/users/john.doe/integrations \
  -H 'Content-Type: application/json' \
  -d '{
    "integration_type": "SLACK",
    "enabled": true,
    "config": {
      "user_email": "john.doe@company.com",
      "workspace_id": "T1234567890",
      "thread_replies": false,
      "mention_user": false,
      "include_agent_info": true
    },
    "priority": 1,
    "retry_count": 3,
    "retry_delay_seconds": 60
  }'

# List user's integrations
curl http://localhost:8080/api/v1/users/john.doe/integrations

# Remove user's Slack integration
curl -X DELETE http://localhost:8080/api/v1/users/john.doe/integrations/SLACK
```

#### Method 4: Manual Database (Legacy)

For advanced users, you can still add users directly to the database:

```bash
kubectl exec -n ${NAMESPACE:-default} pgvector-0 -- psql -U postgres -d rag_blueprint -c "
INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, retry_count, retry_delay_seconds, created_at, updated_at)
VALUES (
  'john.doe', 
  'SLACK', 
  true, 
  '{
    \"user_email\": \"john.doe@company.com\",
    \"workspace_id\": \"T1234567890\",
    \"thread_replies\": false,
    \"mention_user\": false,
    \"include_agent_info\": true
  }'::jsonb,
  1,        -- priority (1 = highest priority)
  3,        -- retry_count (retry up to 3 times)
  60,       -- retry_delay_seconds (wait 60 seconds between retries)
  NOW(),    -- created_at
  NOW()     -- updated_at
);
"
```

### Configuration Options

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_email` | string | Yes* | User's Slack email address |
| `channel_id` | string | Yes* | Specific channel ID (alternative to user_email) |
| `workspace_id` | string | No | Your Slack workspace ID |
| `thread_replies` | boolean | No | Use threads for responses (default: false) |
| `mention_user` | boolean | No | @mention the user (default: false) |
| `include_agent_info` | boolean | No | Show which agent responded (default: true) |
| `thread_ts` | string | No | Reply to specific thread |

*Either `user_email` OR `channel_id` is required

### Database Schema Requirements

The `user_integration_configs` table requires these additional fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `priority` | integer | Yes | Integration priority (1 = highest, higher numbers = lower priority) |
| `retry_count` | integer | Yes | Number of retry attempts on failure (recommended: 3) |
| `retry_delay_seconds` | integer | Yes | Seconds to wait between retries (recommended: 60) |
| `created_at` | timestamp | Yes | Record creation timestamp (use NOW()) |
| `updated_at` | timestamp | Yes | Record update timestamp (use NOW()) |

### Important Notes

- **`workspace_id`**: Currently **optional** and not used by the integration. The bot token already identifies the workspace. This field may be used in future versions for multi-workspace support.
- **User ID**: Replace `'john.doe'` with your actual user identifier in your system. This can be:
  - Your username (e.g., `'john.doe'`)
  - Employee ID (e.g., `'EMP12345'`)
  - Slack User ID (e.g., `'U09EPAXGNLS'`) - found in Slack profile
  - Any unique identifier your system uses
- **Email Address**: Must match the exact email address associated with the Slack user account.

### Practical Example

Here's a real example with actual values:

```bash
kubectl exec -n ${NAMESPACE:-default} pgvector-0 -- psql -U postgres -d rag_blueprint -c "
INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, retry_count, retry_delay_seconds, created_at, updated_at)
VALUES (
  'U09EPAXGNLS',  -- Real Slack User ID
  'SLACK', 
  true, 
  '{
    \"user_email\": \"tchughesiv@gmail.com\",
    \"thread_replies\": true,
    \"mention_user\": true,
    \"include_agent_info\": true
  }'::jsonb,
  1,        -- priority (1 = highest priority)
  3,        -- retry_count (retry up to 3 times)
  60,       -- retry_delay_seconds (wait 60 seconds between retries)
  NOW(),    -- created_at
  NOW()     -- updated_at
);
"
```

**Note**: `workspace_id` is omitted since it's optional and not currently used.

## 🔄 Two-Way Interaction

With the enhanced Slack integration, users can interact with the AI agent directly in Slack:

### **Ways to Interact:**

1. **📱 Direct Messages**: Send a DM to the bot
2. **⚡ Slash Commands**: Use `/agent [your message]` in any channel
3. **💬 @Mentions**: Mention the bot in channels: `@Self-Service Agent help me`
4. **🔘 Interactive Buttons**: Click buttons in agent responses

### **Example Conversation Flow:**

```
User: /agent I need help with my laptop refresh
Bot:  🤖 I can help with laptop refresh! What specific issue are you having?
      [📋 View Session] [💬 Ask Follow-up]

User: How long does it usually take?
Bot:  📝 Laptop refresh typically takes 3-5 business days...
      [📋 View Session] [💬 Ask Follow-up]
```

### **Session Continuity:**
- 🔗 All messages in the same conversation maintain session context
- 📋 Session IDs are tracked automatically  
- 💾 Previous conversation history is remembered
- 🔄 Switch between DMs, channels, and slash commands seamlessly

### Channel ID vs User Email

**For Direct Messages (recommended):**
```json
{
  "user_email": "user@company.com",
  "include_agent_info": true
}
```

**For Specific Channel:**
```json
{
  "channel_id": "C1234567890",
  "mention_user": true,
  "include_agent_info": true
}
```

## Testing the Integration

### Step 1: Send Test Request

```bash
curl -X POST "https://your-request-manager-route/api/v1/requests/generic" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "slack",
    "user_id": "U09EPAXGNLS",
    "content": "Test Slack integration - please confirm this works"
  }'
```

### Step 2: Monitor Logs

```bash
# Watch Integration Dispatcher logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default}

# Look for successful delivery
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} | grep -i "delivered to slack"
```

### Step 3: Check Slack

You should receive a formatted message in Slack with:
- 📝 The agent's response
- 🤖 Agent information (if enabled)
- 🔗 "View Session" button
- ➖ Clean formatting with dividers

## Troubleshooting

### Common Issues

**1. Database constraint error: "null value in column 'priority'"**
- This happens when using the old INSERT format without required fields
- Use the complete INSERT statement with `priority`, `retry_count`, `retry_delay_seconds`, `created_at`, `updated_at`
- See the "Practical Example" section above for the correct format

**2. "Slack bot token not configured"**
- Verify the secret exists: `kubectl get secret self-service-agent-integration-secrets -n ${NAMESPACE:-default}`
- Check the secret has the right key: `kubectl describe secret self-service-agent-integration-secrets -n ${NAMESPACE:-default}`
- Restart the integration dispatcher after creating the secret

**3. "User not found" errors**
- Ensure the email in `user_email` matches the user's Slack profile email
- Check if the user is in the same workspace as the bot
- Verify the bot has `users:read.email` permission

**4. "Channel not found" errors**
- Ensure `channel_id` is correct (starts with C, D, or G)
- Make sure the bot is added to the channel (for public channels)
- For private channels, invite the bot first

**5. Messages not appearing**
- Check Integration Dispatcher logs for errors
- Verify the user has an integration config in the database
- Ensure the request used `integration_type: "slack"`

### Health Check

The Slack integration includes a health check. Monitor it with:

```bash
kubectl logs deployment/self-service-agent-integration-dispatcher -n ${NAMESPACE:-default} | grep -i "slack.*health"
```

## Advanced Features

### Slash Command (Optional)

The app manifest includes a `/agent` slash command. To use it:

1. **Set up Request URL** in Slack app settings under "Slash Commands"
2. **Point to your Integration Dispatcher**: `https://your-route/slack/commands`
3. **Implement the command handler** (not yet implemented in the current system)

### Interactive Elements

The Slack messages include a "View Session" button. To make it interactive:

1. **Set up Interactivity Request URL** in Slack app settings
2. **Point to**: `https://your-route/slack/interactive`
3. **Implement button handlers** (future enhancement)

## Troubleshooting

### App Manifest Issues

**1. "expecting string, number, null, true, false... got INVALID" error**
- **Cause**: YAML parsing issues in Slack's manifest editor
- **Solution**: Use the JSON format instead of YAML (recommended)
- **Steps**:
  1. Copy the JSON manifest from the expandable section above
  2. Replace `YOUR_INTEGRATION_DISPATCHER_ROUTE` with your actual route
  3. Paste into Slack's app manifest editor

**2. "Sending messages to this app has been turned off"**
- **Cause**: Messages tab not enabled in app configuration
- **Solution**: Ensure the manifest includes:
  ```json
  "app_home": {
    "messages_tab_enabled": true,
    "messages_tab_read_only_enabled": false
  }
  ```

**3. Slash commands or events not working**
- **Cause**: Request URLs not properly configured
- **Solution**: Update the manifest URLs to point to your Integration Dispatcher route:
  - Event Subscriptions: `https://your-route/slack/events`
  - Interactivity: `https://your-route/slack/interactive`  
  - Slash Commands: `https://your-route/slack/commands`

### Integration Flow Issues

**4. Database constraint error: "null value in column 'priority'"**
- This happens when using the old INSERT format without required fields
- Use the complete INSERT statement with `priority`, `retry_count`, `retry_delay_seconds`, `created_at`, `updated_at`
- See the "Practical Example" section above for the correct format

**5. "Slack bot token not configured"**
- Verify the secret exists: `kubectl get secret self-service-agent-integration-secrets -n ${NAMESPACE:-default}`
- Check the secret has the right key: `kubectl describe secret self-service-agent-integration-secrets -n ${NAMESPACE:-default}`
- Restart the integration dispatcher after creating the secret

**6. "User not found" errors**
- Ensure the email in `user_email` matches the user's Slack profile email
- Check if the user is in the same workspace as the bot
- Verify the bot has `users:read.email` permission

**7. "Channel not found" errors**
- Ensure `channel_id` is correct (starts with C, D, or G)
- Make sure the bot is added to the channel (for public channels)
- For private channels, invite the bot first

**8. Messages not appearing**
- Check Integration Dispatcher logs for errors
- Verify the user has an integration config in the database
- Ensure the request used `integration_type: "slack"`

### Health Check

Check if the Slack integration is available:

```bash
curl -s "https://your-integration-dispatcher-route/health" | jq .
```

Look for `"SLACK"` in the `integrations_available` array. If missing:
- Check that `SLACK_BOT_TOKEN` environment variable is set
- Verify the bot token is valid (not a placeholder)
- Restart the Integration Dispatcher deployment

## Security Notes

- 🔒 Store bot tokens in Kubernetes secrets, never in code
- 🔐 Use signing secrets to verify requests from Slack
- 🛡️ Limit OAuth scopes to minimum required permissions
- 🔄 Enable token rotation for enhanced security
- 📝 Monitor logs for unauthorized access attempts

## Support

For issues with the Slack integration:

1. Check the Integration Dispatcher logs
2. Verify your app manifest configuration
3. Test with the E2E test script: `./test_e2e_flow.sh`
4. Use the TEST integration first to verify the pipeline works
