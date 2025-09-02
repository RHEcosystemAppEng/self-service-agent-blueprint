# Email Integration Setup Guide

This guide explains how to configure and use email integration in the Self-Service Agent system.

## Overview

The email integration allows users to receive AI agent responses via email. It supports both HTML and plain text formats, with configurable templates and delivery preferences.

## Configuration

### 1. SMTP Server Configuration

Configure your SMTP server settings in the Helm values:

```yaml
security:
  email:
    # SMTP Server Configuration
    smtpHost: "smtp.gmail.com"          # Your SMTP server
    smtpPort: "587"                     # Port (587 for STARTTLS, 465 for SSL)
    smtpUsername: "your-email@gmail.com" # SMTP username
    smtpPassword: "your-app-password"   # SMTP password/app password
    smtpUseTls: "true"                  # Use TLS encryption
    fromEmail: "noreply@yourcompany.com" # From email address
    fromName: "Self-Service Agent"      # From name
```

### 2. User Email Configuration

Users can be configured with individual email preferences:

```yaml
security:
  email:
    # Default settings for all users
    defaultUserConfig:
      format: "html"                    # html or text
      includeAgentInfo: true           # Include agent information
      includeSignature: true           # Include system signature
      replyTo: ""                      # Default reply-to address
      displayName: ""                  # Default display name
    
    # Example user configurations
    exampleUsers:
      admin:
        emailAddress: "admin@company.com"
        format: "html"
        includeAgentInfo: true
        includeSignature: true
        replyTo: "admin@company.com"
        displayName: "Admin User"
        priority: 10
        enabled: true
```

## Deployment

### Using Helm Install

```bash
# Basic email configuration
make helm-install EXTRA_HELM_ARGS="--set security.email.smtpHost=smtp.gmail.com --set security.email.smtpUsername=your-email@gmail.com --set security.email.smtpPassword=your-app-password --set security.email.fromEmail=noreply@yourcompany.com"

# With custom SMTP settings
make helm-install EXTRA_HELM_ARGS="--set security.email.smtpHost=smtp.company.com --set security.email.smtpPort=465 --set security.email.smtpUseTls=true --set security.email.smtpUsername=agent@company.com --set security.email.smtpPassword=secure-password --set security.email.fromEmail=agent@company.com --set security.email.fromName='Company AI Agent'"
```

### Using Helm Upgrade

```bash
# Update existing deployment
helm upgrade self-service-agent ./helm \
  --set security.email.smtpHost=smtp.gmail.com \
  --set security.email.smtpUsername=your-email@gmail.com \
  --set security.email.smtpPassword=your-app-password \
  --set security.email.fromEmail=noreply@yourcompany.com \
  -n your-namespace
```

## User Setup

### 1. Automatic Setup (from Helm values)

Use the provided script to set up example users:

```bash
# Setup example users from Helm values
./scripts/setup-email-users.sh --namespace your-namespace
```

### 2. Manual Database Setup

Connect to the database and insert user configurations:

```bash
# Get database pod
DB_POD=$(kubectl get pods -n your-namespace -l app.kubernetes.io/name=pgvector -o jsonpath='{.items[0].metadata.name}')

# Insert user email configuration
kubectl exec -n your-namespace $DB_POD -- psql -U postgres -d rag_blueprint -c "
INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, retry_count, retry_delay_seconds, created_by) VALUES
('your-user-id', 'EMAIL', true, '{\"email_address\": \"user@company.com\", \"format\": \"html\", \"include_agent_info\": true, \"include_signature\": true, \"reply_to\": \"user@company.com\", \"display_name\": \"Your Name\"}', 5, 3, 60, 'manual-setup')
ON CONFLICT (user_id, integration_type) DO UPDATE SET
  enabled = EXCLUDED.enabled,
  config = EXCLUDED.config,
  priority = EXCLUDED.priority,
  updated_at = CURRENT_TIMESTAMP;
"
```

### 3. API Setup (Future)

User configurations can also be managed via API endpoints (when implemented):

```bash
# Example API call (not yet implemented)
curl -X POST http://your-integration-dispatcher/api/v1/users/your-user-id/integrations/email \
  -H "Content-Type: application/json" \
  -d '{
    "email_address": "user@company.com",
    "format": "html",
    "include_agent_info": true,
    "include_signature": true,
    "reply_to": "user@company.com",
    "display_name": "Your Name",
    "enabled": true,
    "priority": 5
  }'
```

## Testing

### 1. Health Check

Verify email integration is working:

```bash
# Check integration dispatcher health
curl -s http://your-integration-dispatcher/health | jq '.integrations_available'

# Should include "EMAIL" in the list
```

### 2. Test Email Delivery

Trigger an AI agent conversation and check if email is delivered:

```bash
# Trigger conversation via Request Manager
curl -X POST http://your-request-manager/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "your-user-id",
    "content": "Hello, please help me with my laptop",
    "integration_type": "EMAIL"
  }'

# Check delivery logs
kubectl exec -n your-namespace $DB_POD -- psql -U postgres -d rag_blueprint -c "
SELECT request_id, user_id, integration_type, status, delivered_at, error_message 
FROM delivery_logs 
WHERE integration_type = 'EMAIL' 
ORDER BY created_at DESC 
LIMIT 5;
"
```

### 3. SMTP Connectivity Test

Test SMTP connectivity from within the cluster:

```bash
# Test SMTP connection
kubectl exec -n your-namespace deployment/self-service-agent-integration-dispatcher -- python3 -c "
import asyncio
import aiosmtplib
from email.mime.text import MIMEText

async def test_smtp():
    msg = MIMEText('Test email')
    msg['Subject'] = 'SMTP Test'
    msg['From'] = 'test@example.com'
    msg['To'] = 'test@example.com'
    
    try:
        await aiosmtplib.send(
            msg,
            hostname='smtp.gmail.com',
            port=587,
            username='your-email@gmail.com',
            password='your-app-password',
            use_tls=False,
            start_tls=True
        )
        print('✅ SMTP test successful')
    except Exception as e:
        print(f'❌ SMTP test failed: {e}')

asyncio.run(test_smtp())
"
```

## Configuration Options

### Email Format Options

- **HTML**: Rich formatting with styling and structure
- **Text**: Plain text format for simple email clients

### User Configuration Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `email_address` | string | User's email address | Required |
| `format` | string | Email format (html/text) | html |
| `include_agent_info` | boolean | Include agent information | true |
| `include_signature` | boolean | Include system signature | true |
| `reply_to` | string | Reply-to email address | "" |
| `display_name` | string | User's display name | "" |
| `priority` | integer | Delivery priority (higher = more important) | 5 |
| `enabled` | boolean | Enable/disable email delivery | true |

### SMTP Configuration Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `smtpHost` | string | SMTP server hostname | "" |
| `smtpPort` | string | SMTP server port | 587 |
| `smtpUsername` | string | SMTP username | "" |
| `smtpPassword` | string | SMTP password | "" |
| `smtpUseTls` | string | Use TLS encryption | true |
| `fromEmail` | string | From email address | noreply@selfservice.local |
| `fromName` | string | From name | Self-Service Agent |

## Troubleshooting

### Common Issues

1. **Email not showing in health check**
   - Check SMTP credentials in Kubernetes secrets
   - Verify network connectivity to SMTP server
   - Check integration dispatcher logs

2. **SMTP authentication failed**
   - Verify username and password
   - For Gmail, use App Passwords instead of regular password
   - Check if 2FA is enabled and requires app password

3. **Connection timeout**
   - Check network policies allow outbound SMTP traffic
   - Verify SMTP server hostname and port
   - Test connectivity from within the cluster

4. **Emails not delivered**
   - Check user integration configuration in database
   - Verify email address is correct
   - Check delivery logs for error messages

### Debug Commands

```bash
# Check integration dispatcher logs
kubectl logs -n your-namespace deployment/self-service-agent-integration-dispatcher --tail=50

# Check email integration health
kubectl exec -n your-namespace deployment/self-service-agent-integration-dispatcher -- curl -s http://localhost:8080/health | jq '.integrations_available'

# Check user configurations
kubectl exec -n your-namespace $DB_POD -- psql -U postgres -d rag_blueprint -c "SELECT * FROM user_integration_configs WHERE integration_type = 'EMAIL';"

# Check delivery logs
kubectl exec -n your-namespace $DB_POD -- psql -U postgres -d rag_blueprint -c "SELECT * FROM delivery_logs WHERE integration_type = 'EMAIL' ORDER BY created_at DESC LIMIT 10;"
```

## Security Considerations

1. **SMTP Credentials**: Store SMTP passwords in Kubernetes secrets, not in Helm values
2. **TLS Encryption**: Always use TLS/SSL for SMTP connections
3. **App Passwords**: Use app-specific passwords for Gmail and other providers
4. **Network Policies**: Restrict outbound SMTP traffic to known servers
5. **Email Validation**: Validate email addresses before storing in database

## Examples

### Gmail Configuration

```yaml
security:
  email:
    smtpHost: "smtp.gmail.com"
    smtpPort: "587"
    smtpUsername: "your-email@gmail.com"
    smtpPassword: "your-16-char-app-password"  # Use App Password
    smtpUseTls: "true"
    fromEmail: "your-email@gmail.com"
    fromName: "Your Company AI Agent"
```

### Corporate SMTP Configuration

```yaml
security:
  email:
    smtpHost: "mail.company.com"
    smtpPort: "587"
    smtpUsername: "ai-agent@company.com"
    smtpPassword: "secure-corporate-password"
    smtpUseTls: "true"
    fromEmail: "ai-agent@company.com"
    fromName: "Company AI Assistant"
```

### Office 365 Configuration

```yaml
security:
  email:
    smtpHost: "smtp.office365.com"
    smtpPort: "587"
    smtpUsername: "ai-agent@company.onmicrosoft.com"
    smtpPassword: "office365-password"
    smtpUseTls: "true"
    fromEmail: "ai-agent@company.onmicrosoft.com"
    fromName: "Company AI Agent"
```

## 4. Default Email Behavior

The email integration uses the following default values when user-specific configurations are not provided:

### System Defaults

| Setting | Default Value | Description |
|---------|---------------|-------------|
| `format` | `"html"` | Email format (html or text) |
| `include_agent_info` | `true` | Include agent ID in email body |
| `include_signature` | `true` | Include system signature |
| `reply_to` | Not set | No reply-to address by default |
| `display_name` | Not set | No custom display name by default |

### How Defaults Work

- **User-specific configs override defaults**: If a user has a configuration in the database, their settings take precedence
- **System defaults apply when no user config exists**: Users without specific configurations get the system defaults
- **Defaults are hardcoded in the integration**: These values are built into the email integration code

## 5. User Email Configuration Examples

The following are example user configurations that can be used as templates or for testing. These examples show different types of users and their email preferences:

### Example User Configurations

```yaml
# Example User Email Configurations
# These can be used as templates or for testing
# Users can be configured via database or API calls

exampleUsers:
  # Example: Admin user with full email features
  admin:
    emailAddress: "admin@company.com"
    format: "html"
    includeAgentInfo: true
    includeSignature: true
    replyTo: "admin@company.com"
    displayName: "Admin User"
    priority: 10  # Higher priority = more important
    enabled: true

  # Example: Regular user with basic email
  user:
    emailAddress: "user@company.com"
    format: "text"
    includeAgentInfo: true
    includeSignature: true
    replyTo: ""
    displayName: "Regular User"
    priority: 5
    enabled: true

  # Example: Test user for development
  test:
    emailAddress: "test@example.com"
    format: "html"
    includeAgentInfo: false
    includeSignature: false
    replyTo: "test@example.com"
    displayName: "Test User"
    priority: 1
    enabled: false  # Disabled by default
```

### User Configuration Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `emailAddress` | String | User's email address | `"user@company.com"` |
| `format` | String | Email format: `"html"` or `"text"` | `"html"` |
| `includeAgentInfo` | Boolean | Include agent ID in email body | `true` |
| `includeSignature` | Boolean | Include system signature | `true` |
| `replyTo` | String | Reply-to address (empty for no reply) | `"user@company.com"` |
| `displayName` | String | Display name in email clients | `"John Doe"` |
| `priority` | Integer | Priority level (higher = more important) | `5` |
| `enabled` | Boolean | Whether this integration is active | `true` |

### Overriding Defaults

To override the system defaults for specific users, you can set these values in the user's configuration:

```json
{
  "email_address": "user@company.com",
  "format": "text",                    // Override default "html"
  "include_agent_info": false,         // Override default true
  "include_signature": false,          // Override default true
  "reply_to": "user@company.com",      // Add reply-to address
  "display_name": "John Doe"           // Add display name
}
```

### Setting Up Users

To create these user configurations in your database, you can:

1. **Use the setup script** (if updated to process Helm values):
   ```bash
   ./scripts/setup-email-users.sh
   ```

2. **Manual database insertion**:
   ```sql
   INSERT INTO user_integration_configs (user_id, integration_type, enabled, config, priority, created_at, updated_at)
   VALUES (
     'admin',
     'EMAIL',
     true,
     '{"email_address": "admin@company.com", "format": "html", "include_agent_info": true, "include_signature": true, "reply_to": "admin@company.com", "display_name": "Admin User"}'::jsonb,
     10,
     NOW(),
     NOW()
   );
   ```

3. **API calls** (if user management endpoints are available):
   ```bash
   curl -X POST http://your-api/api/v1/users/admin/integrations \
     -H "Content-Type: application/json" \
     -d '{"integration_type": "EMAIL", "enabled": true, "config": {...}}'
   ```
