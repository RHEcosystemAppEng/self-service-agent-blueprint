# Authentication Guide

This guide explains how to configure and use authentication in the Self-Service Agent system.

## Overview

The system supports multiple authentication methods for web endpoint requests:

1. **JWT Authentication** - Industry standard token-based authentication
2. **API Key Authentication** - Simple key-based authentication for testing and internal tools
3. **Service Mesh Authentication** - Legacy support for Istio-injected headers

## Configuration

### 1. JWT Authentication

JWT authentication provides secure, stateless authentication using industry-standard tokens.

#### Helm Configuration

```yaml
security:
  jwt:
    enabled: true  # Set to true to enable JWT validation
    issuers:
      # Red Hat SSO Example
      - issuer: "https://sso.redhat.com/auth/realms/redhat-external"
        jwksUri: "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs"
        audience: "selfservice-api"
        algorithms: ["RS256"]
      # Custom OIDC Provider Example
      - issuer: "https://auth.company.com"
        jwksUri: "https://auth.company.com/.well-known/jwks.json"
        audience: "selfservice-api"
        algorithms: ["RS256", "HS256"]
    validation:
      verifySignature: true
      verifyExpiration: true
      verifyAudience: true
      verifyIssuer: true
      leeway: 60  # Seconds of leeway for clock skew
```

#### Environment Variables

```bash
JWT_ENABLED=true
JWT_ISSUERS='[{"issuer":"https://sso.redhat.com/auth/realms/redhat-external","jwksUri":"https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs","audience":"selfservice-api","algorithms":["RS256"]}]'
JWT_VERIFY_SIGNATURE=true
JWT_VERIFY_EXPIRATION=true
JWT_VERIFY_AUDIENCE=true
JWT_VERIFY_ISSUER=true
JWT_LEEWAY=60
```

### 2. API Key Authentication

API key authentication provides simple authentication for testing and internal tools.

#### Helm Configuration

```yaml
security:
  apiKeys:
    enabled: true  # Always enabled as fallback
    webKeys:
      # Format: "key-name": "user-email"
      "web-test-user": "test@company.com"
      "web-admin": "admin@company.com"
      "web-demo": "demo@company.com"
```

#### Environment Variables

```bash
API_KEYS_ENABLED=true
WEB_API_KEYS='{"web-test-user":"test@company.com","web-admin":"admin@company.com","web-demo":"demo@company.com"}'
```

## Usage Examples

### 1. JWT Authentication

#### Getting a JWT Token

```bash
# Example: Get token from Red Hat SSO
curl -X POST https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=your-client-id&client_secret=your-client-secret"
```

#### Using JWT Token

```bash
# Send request with JWT token
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "john.doe",
    "content": "Hello, I need help with my laptop",
    "client_ip": "192.168.1.100"
  }'
```

### 2. API Key Authentication

```bash
# Send request with API key
curl -X POST https://your-request-manager/api/v1/requests/web \
  -H "Authorization: Bearer web-test-user" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "web-test-user",
    "content": "Hello, I need help with my laptop",
    "client_ip": "192.168.1.100"
  }'
```

### 3. Python Client Example

```python
import httpx
import jwt

# JWT Authentication
def get_jwt_token():
    # Your JWT token acquisition logic here
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

async def send_web_request():
    token = get_jwt_token()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://your-request-manager/api/v1/requests/web",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "user_id": "john.doe",
                "content": "Hello, I need help with my laptop",
                "client_ip": "192.168.1.100"
            }
        )
        return response.json()

# API Key Authentication
async def send_web_request_with_api_key():
    api_key = "web-test-user"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://your-request-manager/api/v1/requests/web",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "user_id": api_key,  # Use API key as user ID
                "content": "Hello, I need help with my laptop",
                "client_ip": "192.168.1.100"
            }
        )
        return response.json()
```

## Deployment

### Using Helm Install

```bash
# Enable JWT authentication
make helm-install EXTRA_HELM_ARGS="--set security.jwt.enabled=true --set security.jwt.issuers[0].issuer=https://sso.redhat.com/auth/realms/redhat-external --set security.jwt.issuers[0].jwksUri=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs --set security.jwt.issuers[0].audience=selfservice-api"

# Enable API key authentication (default)
make helm-install EXTRA_HELM_ARGS="--set security.apiKeys.enabled=true --set security.apiKeys.webKeys.web-test-user=test@company.com"

# Both JWT and API key authentication
make helm-install EXTRA_HELM_ARGS="--set security.jwt.enabled=true --set security.apiKeys.enabled=true"
```

### Using Helm Upgrade

```bash
# Enable JWT authentication
helm upgrade self-service-agent ./helm \
  --set security.jwt.enabled=true \
  --set security.jwt.issuers[0].issuer=https://sso.redhat.com/auth/realms/redhat-external \
  --set security.jwt.issuers[0].jwksUri=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs \
  --set security.jwt.issuers[0].audience=selfservice-api \
  -n your-namespace

# Configure API keys
helm upgrade self-service-agent ./helm \
  --set security.apiKeys.webKeys.web-test-user=test@company.com \
  --set security.apiKeys.webKeys.web-admin=admin@company.com \
  -n your-namespace
```

## Authentication Flow

```mermaid
graph TD
    A[Client sends request with Authorization header] --> B[FastAPI HTTPBearer extracts token]
    B --> C[get_current_user function]
    C --> D{JWT enabled?}
    D -->|Yes| E[validate_jwt_token]
    E --> F{JWT valid?}
    F -->|Yes| G[Return user info from JWT]
    F -->|No| H{API keys enabled?}
    D -->|No| H
    H -->|Yes| I[verify_web_api_key]
    I --> J{API key valid?}
    J -->|Yes| K[Return user info from API key]
    J -->|No| L[Check service mesh headers]
    L --> M{Headers present?}
    M -->|Yes| N[Return user info from headers]
    M -->|No| O[Return None - Unauthorized]
    G --> P[Web endpoint validates user_id match]
    K --> P
    N --> P
    O --> Q[Web endpoint rejects request]
    P --> R[Request processed]
```

## Security Considerations

### JWT Security

1. **Signature Verification**: Always verify JWT signatures in production
2. **Expiration**: Use short-lived tokens and implement refresh logic
3. **Audience Validation**: Validate the audience claim
4. **Issuer Validation**: Validate the issuer claim
5. **Algorithm Validation**: Only allow secure algorithms (RS256, ES256)

### API Key Security

1. **Key Rotation**: Regularly rotate API keys
2. **Key Storage**: Store API keys securely (Kubernetes secrets)
3. **Key Scope**: Limit API key permissions
4. **Key Monitoring**: Monitor API key usage

### General Security

1. **HTTPS Only**: Always use HTTPS in production
2. **Rate Limiting**: Implement rate limiting for authentication endpoints
3. **Logging**: Log authentication attempts and failures
4. **Monitoring**: Monitor authentication metrics

## Troubleshooting

### Common Issues

1. **JWT Token Invalid**
   ```bash
   # Check JWT configuration
   kubectl exec -n your-namespace deployment/self-service-agent-request-manager -- env | grep JWT
   
   # Check JWT token format
   echo "your-jwt-token" | base64 -d | jq .
   ```

2. **API Key Not Working**
   ```bash
   # Check API key configuration
   kubectl exec -n your-namespace deployment/self-service-agent-request-manager -- env | grep API_KEYS
   
   # Verify API key in request
   curl -v -X POST https://your-request-manager/api/v1/requests/web \
     -H "Authorization: Bearer your-api-key"
   ```

3. **Authentication Not Working**
   ```bash
   # Check request manager logs
   kubectl logs -n your-namespace deployment/self-service-agent-request-manager --tail=50
   
   # Test health endpoint
   curl https://your-request-manager/health
   ```

### Debug Commands

```bash
# Check authentication configuration
kubectl exec -n your-namespace deployment/self-service-agent-request-manager -- env | grep -E "(JWT|API_KEYS)"

# Test JWT token validation
kubectl exec -n your-namespace deployment/self-service-agent-request-manager -- python3 -c "
import jwt
import json
token = 'your-jwt-token'
try:
    payload = jwt.decode(token, options={'verify_signature': False})
    print(json.dumps(payload, indent=2))
except Exception as e:
    print(f'Error: {e}')
"

# Test API key validation
kubectl exec -n your-namespace deployment/self-service-agent-request-manager -- python3 -c "
import json
import os
web_keys = json.loads(os.getenv('WEB_API_KEYS', '{}'))
print('Configured API keys:', web_keys)
print('Test key exists:', 'web-test-user' in web_keys)
"
```

## Migration Guide

### From Service Mesh to JWT

1. **Enable JWT authentication**:
   ```bash
   helm upgrade self-service-agent ./helm \
     --set security.jwt.enabled=true \
     --set security.jwt.issuers[0].issuer=https://your-auth-provider.com \
     -n your-namespace
   ```

2. **Update client applications** to use JWT tokens instead of relying on service mesh headers

3. **Test authentication** with both methods during transition

4. **Disable service mesh authentication** once JWT is working

### From No Authentication to API Keys

1. **Configure API keys**:
   ```bash
   helm upgrade self-service-agent ./helm \
     --set security.apiKeys.webKeys.web-test-user=test@company.com \
     -n your-namespace
   ```

2. **Update client applications** to include Authorization headers

3. **Test with API keys** before enabling JWT

## Best Practices

1. **Start with API Keys**: Use API keys for initial testing and development
2. **Gradual Migration**: Migrate to JWT authentication gradually
3. **Monitor Authentication**: Set up monitoring for authentication failures
4. **Documentation**: Keep authentication configuration documented
5. **Testing**: Test authentication with different scenarios
6. **Security Review**: Regularly review authentication configuration

## Examples

### Complete Configuration Example

```yaml
security:
  jwt:
    enabled: true
    issuers:
      - issuer: "https://sso.redhat.com/auth/realms/redhat-external"
        jwksUri: "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs"
        audience: "selfservice-api"
        algorithms: ["RS256"]
    validation:
      verifySignature: true
      verifyExpiration: true
      verifyAudience: true
      verifyIssuer: true
      leeway: 60
  apiKeys:
    enabled: true
    webKeys:
      "web-test-user": "test@company.com"
      "web-admin": "admin@company.com"
      "web-demo": "demo@company.com"
```

### Complete Client Example

```python
import httpx
import asyncio

async def test_authentication():
    base_url = "https://your-request-manager"
    
    # Test with API key
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/v1/requests/web",
            headers={
                "Authorization": "Bearer web-test-user",
                "Content-Type": "application/json"
            },
            json={
                "user_id": "web-test-user",
                "content": "Test message",
                "client_ip": "192.168.1.100"
            }
        )
        print(f"API Key Response: {response.status_code}")
    
    # Test with JWT token
    jwt_token = "your-jwt-token"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/v1/requests/web",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json"
            },
            json={
                "user_id": "john.doe",
                "content": "Test message",
                "client_ip": "192.168.1.100"
            }
        )
        print(f"JWT Response: {response.status_code}")

if __name__ == "__main__":
    asyncio.run(test_authentication())
```
