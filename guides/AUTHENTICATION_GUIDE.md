# Authentication Guide

This guide explains how to configure and use authentication in the Self-Service Agent system.

## Overview

The system supports multiple authentication methods for web endpoint requests:

1. **JWT Authentication** - Industry standard token-based authentication ⚠️ **NOT PRODUCTION READY**
2. **API Key Authentication** - Simple key-based authentication for testing and internal tools ✅ **PRODUCTION READY**

## 🚨 **Production Readiness Status**

| Authentication Method | Status | Security Level | Production Ready |
|----------------------|--------|----------------|------------------|
| **API Key Authentication** | ✅ Complete | High | ✅ **YES - RECOMMENDED** |
| **Legacy Header Authentication** | ✅ Complete | Medium | ✅ Yes (if behind secure proxy) |
| **Slack Signature Verification** | ✅ Complete | High | ✅ Yes |
| **JWT Authentication** | ⚠️ Partial | Low* | ❌ **NO - NOT SECURE** |

*JWT without signature verification is not secure for production use.

**⚠️ WARNING: JWT signature verification is NOT implemented. Do not use JWT authentication in production.**

## Configuration

### 1. JWT Authentication ⚠️ **NOT PRODUCTION READY**

**⚠️ WARNING: JWT signature verification is NOT implemented. This authentication method is NOT secure for production use.**

JWT authentication provides secure, stateless authentication using industry-standard tokens. However, the current implementation is incomplete and should only be used for development and testing.

#### Current Limitations:
- ❌ **No signature verification** - Tokens can be forged
- ❌ **No JWKS integration** - Cannot verify tokens from external identity providers  
- ❌ **Security risk** - Anyone can create a valid-looking JWT token
- ✅ **Basic validation** - Token structure, issuer, audience, and expiration are validated

#### For Production Use:
Use **API Key Authentication** instead, which is fully implemented and secure.

#### Helm Configuration

```yaml
security:
  jwt:
    enabled: true  # Set to true to enable JWT validation
    issuers:
      # Internal OIDC Provider
      - issuer: "https://auth.acme.com"
        jwksUri: "https://auth.acme.com/.well-known/jwks.json"
        audience: "selfservice-api"
        algorithms: ["RS256"]
      # External Identity Provider
      - issuer: "https://idp.partner.com/oauth2"
        jwksUri: "https://idp.partner.com/oauth2/keys"
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
JWT_ISSUERS='[{"issuer":"https://auth.acme.com","jwksUri":"https://auth.acme.com/.well-known/jwks.json","audience":"selfservice-api","algorithms":["RS256"]}]'
JWT_VERIFY_SIGNATURE=true
JWT_VERIFY_EXPIRATION=true
JWT_VERIFY_AUDIENCE=true
JWT_VERIFY_ISSUER=true
JWT_LEEWAY=60
```

### 2. API Key Authentication ✅ **PRODUCTION READY**

**✅ RECOMMENDED: API Key Authentication is fully implemented and secure for production use.**

API key authentication provides simple authentication for testing and internal tools. This is the **recommended authentication method** for production deployments.

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

### 1. JWT Authentication ⚠️ **NOT PRODUCTION READY**

**⚠️ WARNING: These examples are for development/testing only. JWT signature verification is NOT implemented.**

#### Getting a JWT Token

```bash
# Example: Get token from OIDC provider
curl -X POST https://auth.acme.com/oauth/token \
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

### 2. API Key Authentication ✅ **RECOMMENDED FOR PRODUCTION**

**✅ This is the recommended authentication method for production use.**

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

### 3. Generic Endpoint (No Authentication)

```bash
# Send request without authentication
curl -X POST https://your-request-manager/api/v1/requests/generic \
  -H "Content-Type: application/json" \
  -d '{
    "integration_type": "web",
    "user_id": "anonymous-user",
    "content": "Hello, I need help with my laptop"
  }'
```

### 4. Python Client Example

```python
import httpx
import jwt

# JWT Authentication
def get_jwt_token():
    # Your JWT token acquisition logic here
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

async def send_web_request():
    token = get_jwt_token()
    
    # Using the shared request manager client with JWT authentication
    client = RequestManagerClient(
        request_manager_url="https://your-request-manager",
        user_id="john.doe"
    )
    
    try:
        # Add JWT token to headers
        client.client.headers.update({
            "Authorization": f"Bearer {token}"
        })
        
        response = await client.send_request(
            content="Hello, I need help with my laptop",
            integration_type="WEB",
            endpoint="web",
            metadata={
                "client_ip": "192.168.1.100"
            }
        )
        return response
    finally:
        await client.close()

# API Key Authentication
async def send_web_request_with_api_key():
    api_key = "web-test-user"
    
    # Using the shared request manager client with API key authentication
    client = RequestManagerClient(
        request_manager_url="https://your-request-manager",
        user_id=api_key  # Use API key as user ID
    )
    
    try:
        # Add API key to headers
        client.client.headers.update({
            "Authorization": f"Bearer {api_key}"
        })
        
        response = await client.send_request(
            content="Hello, I need help with my laptop",
            integration_type="WEB",
            endpoint="web",
            metadata={
                "client_ip": "192.168.1.100"
            }
        )
        return response
    finally:
        await client.close()

# No Authentication (Generic endpoint)
from shared_clients import RequestManagerClient

# Note: Using the RequestManagerClient provides several benefits:
# - Built-in retry logic and error handling
# - Consistent API interface across all endpoints
# - HTTP/2 support and connection pooling
# - Proper resource cleanup
# - Standardized request/response handling

async def send_generic_request():
    # Using the shared request manager client
    client = RequestManagerClient(
        request_manager_url="https://your-request-manager",
        user_id="anonymous-user"
    )
    
    try:
        response = await client.send_request(
            content="Hello, I need help with my laptop",
            integration_type="WEB",
            endpoint="generic"
        )
        return response
    finally:
        await client.close()

# Alternative: Using the client as a context manager
async def send_generic_request_with_context():
    async with RequestManagerClient(
        request_manager_url="https://your-request-manager",
        user_id="anonymous-user"
    ) as client:
        return await client.send_request(
            content="Hello, I need help with my laptop",
            integration_type="WEB",
            endpoint="generic"
        )
```

## Deployment

### Choosing the Right Deployment Mode

The authentication configuration works across all deployment modes:

- **Development Mode** (`helm-install-dev`): Use for local development and testing authentication
- **Testing Mode** (`helm-install-test`): Use for CI/CD testing with authentication
- **Production Mode** (`helm-install-prod`): Use for production deployments with authentication

### Using Helm Install

```bash
# Development deployment with JWT authentication
make helm-install-dev EXTRA_HELM_ARGS="--set security.jwt.enabled=true --set security.jwt.issuers[0].issuer=https://auth.acme.com --set security.jwt.issuers[0].jwksUri=https://auth.acme.com/.well-known/jwks.json --set security.jwt.issuers[0].audience=selfservice-api"

# Development deployment with API key authentication
make helm-install-dev EXTRA_HELM_ARGS="--set security.apiKeys.webKeys.web-test-user=test@company.com"

# Production deployment with JWT authentication
make helm-install-prod EXTRA_HELM_ARGS="--set security.jwt.enabled=true --set security.jwt.issuers[0].issuer=https://auth.acme.com --set security.jwt.issuers[0].jwksUri=https://auth.acme.com/.well-known/jwks.json --set security.jwt.issuers[0].audience=selfservice-api"

# Production deployment with both JWT and API key authentication
make helm-install-prod EXTRA_HELM_ARGS="--set security.jwt.enabled=true --set security.apiKeys.webKeys.web-test-user=test@company.com"
```

### Using Helm Upgrade

```bash
# Enable JWT authentication
helm upgrade self-service-agent ./helm \
  --set security.jwt.enabled=true \
  --set security.jwt.issuers[0].issuer=https://auth.acme.com \
  --set security.jwt.issuers[0].jwksUri=https://auth.acme.com/.well-known/jwks.json \
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
    J -->|No| L[Check HTTP headers]
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

1. **Signature Verification**: ⚠️ **Currently disabled** - JWT signature verification is not yet implemented
2. **Expiration**: Use short-lived tokens and implement refresh logic
3. **Audience Validation**: Validate the audience claim
4. **Issuer Validation**: Validate the issuer claim
5. **Algorithm Validation**: Only allow secure algorithms (RS256, ES256)

**Note**: JWT signature verification is currently disabled in the implementation. This should be enabled for production use by implementing proper JWKS fetching and signature verification.

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

### Authentication Method Options

The system supports multiple authentication methods that can be used independently or together:

1. **JWT Authentication** (Recommended for production):
   ```bash
   helm upgrade self-service-agent ./helm \
     --set security.jwt.enabled=true \
     --set security.jwt.issuers[0].issuer=https://your-auth-provider.com \
     -n your-namespace
   ```

2. **API Key Authentication** (For testing and internal tools):
   ```bash
   helm upgrade self-service-agent ./helm \
     --set security.apiKeys.webKeys."web-test-user"="test@company.com" \
     -n your-namespace
   ```

3. **Legacy Header Authentication** (For reverse proxy setups):
   - Headers: `x-user-id`, `x-user-email`, `x-user-groups`
   - Used when authentication is handled by upstream systems (reverse proxies, load balancers)
   - No configuration needed - automatically enabled

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
      - issuer: "https://auth.acme.com"
        jwksUri: "https://auth.acme.com/.well-known/jwks.json"
        audience: "selfservice-api"
        algorithms: ["RS256"]
    validation:
      verifySignature: true
      verifyExpiration: true
      verifyAudience: true
      verifyIssuer: true
      leeway: 60
  apiKeys:
    webKeys:
      "web-test-user": "test@company.com"
      "web-admin": "admin@company.com"
      "web-demo": "demo@company.com"
```

### Complete Client Example

```python
from shared_clients import RequestManagerClient
import asyncio

async def test_authentication():
    base_url = "https://your-request-manager"
    
    # Test with API key
    api_client = RequestManagerClient(
        request_manager_url=base_url,
        user_id="web-test-user"
    )
    
    try:
        # Add API key to headers
        api_client.client.headers.update({
            "Authorization": "Bearer web-test-user"
        })
        
        response = await api_client.send_request(
            content="Test message",
            integration_type="WEB",
            endpoint="web",
            metadata={
                "client_ip": "192.168.1.100"
            }
        )
        print(f"API Key Response: {response}")
    finally:
        await api_client.close()
    
    # Test with JWT token
    jwt_token = "your-jwt-token"
    jwt_client = RequestManagerClient(
        request_manager_url=base_url,
        user_id="john.doe"
    )
    
    try:
        # Add JWT token to headers
        jwt_client.client.headers.update({
            "Authorization": f"Bearer {jwt_token}"
        })
        
        response = await jwt_client.send_request(
            content="Test message",
            integration_type="WEB",
            endpoint="web",
            metadata={
                "client_ip": "192.168.1.100"
            }
        )
        print(f"JWT Response: {response}")
    finally:
        await jwt_client.close()

if __name__ == "__main__":
    asyncio.run(test_authentication())
```

