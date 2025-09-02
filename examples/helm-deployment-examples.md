# Helm Deployment Examples with Request Management Layer

This document provides examples of deploying the Self-Service Agent Blueprint with the Request Management Layer.

## Prerequisites

1. **OpenShift Cluster** with appropriate permissions
2. **OpenShift Serverless Operator** installed (for Knative Eventing)
3. **Streams for Apache Kafka** installed (for Kafka cluster and KafkaNodePool resources)
4. **Helm 3.x** installed

## Basic Deployment (No Request Management Layer)

Deploy just the core Self-Service Agent components:

```bash
make helm-install NAMESPACE=my-namespace
```

This deploys:
- Asset Manager
- Llama Stack with PostgreSQL persistence
- MCP Servers (Employee Info, ServiceNow)

## Request Management Layer Deployment

Enable the Request Management Layer with Knative eventing for event-driven architecture:

```bash
make helm-install \
  NAMESPACE=my-namespace \
  REQUEST_MANAGEMENT=true \
  KNATIVE_EVENTING=true
```

This adds:
- Request Manager (Deployment + Service)
- Agent Service (Deployment + Service)  
- Integration Dispatcher (Deployment + Service)
- Knative Broker and Triggers for event-driven architecture
- OpenShift Routes for external access

## Production Deployment with External Secrets

For production, use external secret management:

```bash
# Create TLS certificate secret
kubectl create secret tls selfservice-tls-secret \
  --cert=tls.crt \
  --key=tls.key \
  -n my-namespace

# Deploy with external secrets
make helm-install \
  NAMESPACE=my-namespace \
  REQUEST_MANAGEMENT=true \
  KNATIVE_EVENTING=true \
  EXTRA_HELM_ARGS="--set security.apiKeys.snowIntegration= --set security.slack.signingSecret="

# Update secrets after deployment
kubectl patch secret api-keys -n my-namespace \
  --patch='{"data":{"snow-integration":"'$(echo -n "your-real-snow-api-key" | base64)'"}}'

kubectl patch secret slack-signing-secret -n my-namespace \
  --patch='{"data":{"signing-secret":"'$(echo -n "your-real-slack-secret" | base64)'"}}'
```

## Multi-Environment Configuration

### Development Environment
```bash
make helm-install \
  NAMESPACE=dev-selfservice \
  REQUEST_MANAGEMENT=true \
  KNATIVE_EVENTING=true \
  LLM=llama-3-2-1b-instruct \
  SAFETY=llama-guard-3-1b
```

### Staging Environment
```bash
make helm-install \
  NAMESPACE=staging-selfservice \
  REQUEST_MANAGEMENT=true \
  KNATIVE_EVENTING=true \
  LLM=llama-3-2-3b-instruct \
  SAFETY=llama-guard-3-1b
```

### Production Environment
```bash
make helm-install \
  NAMESPACE=prod-selfservice \
  REQUEST_MANAGEMENT=true \
  KNATIVE_EVENTING=true \
  LLM=llama-3-1-70b-instruct \
  SAFETY=llama-guard-3-8b \
  SLACK_SIGNING_SECRET=${SLACK_SECRET} \
  SNOW_API_KEY=${SNOW_API_KEY} \
  HR_API_KEY=${HR_API_KEY}
```

## Custom Configuration with values.yaml

Create a custom values file for complex configurations:

```yaml
# custom-values.yaml
requestManagement:
  enabled: true
  serviceMesh:
    enabled: true
    gateway:
      hosts:
        - "api.selfservice.apps.cluster.local"
        - "chat.selfservice.apps.cluster.local"
      tls:
        secretName: "custom-tls-secret"
  
  requestManager:
    resources:
      requests:
        memory: "512Mi"
        cpu: "200m"
      limits:
        memory: "1Gi"
        cpu: "1000m"
    autoscaling:
      minScale: 2
      maxScale: 20
      target: 5
  
  agentService:
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "2000m"

security:
  jwt:
    issuers:
      - issuer: "https://sso.company.com/auth/realms/employees"
        jwksUri: "https://sso.company.com/auth/realms/employees/protocol/openid-connect/certs"
        audience: "selfservice-api"
```

Deploy with custom values:

```bash
make helm-install \
  NAMESPACE=my-namespace \
  EXTRA_HELM_ARGS="-f custom-values.yaml"
```

## Verification and Testing

After deployment, verify the installation:

```bash
# Check deployment status
make helm-status NAMESPACE=my-namespace

# Test health endpoints
kubectl port-forward svc/self-service-agent-request-manager 8080:80 -n my-namespace
curl http://localhost:8080/health

# Test via Service Mesh Gateway (if enabled)
curl -k https://api.selfservice.apps.cluster.local/health

# Check Service Mesh configuration (if enabled)
kubectl get gateway,virtualservice,authorizationpolicy -n my-namespace

# Check Knative Eventing resources
kubectl get broker,trigger -n my-namespace

# View deployment notes
helm get notes self-service-agent -n my-namespace
```

## Integration Testing

### Web Request Test (with JWT)
```bash
# Get JWT token from your auth provider
TOKEN="your-jwt-token"

curl -X POST https://api.selfservice.apps.cluster.local/api/v1/requests/web \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test.user",
    "content": "Hello, I need help with my laptop",
    "client_ip": "192.168.1.1"
  }'
```

### Tool Request Test (with API Key)
```bash
curl -X POST https://api.selfservice.apps.cluster.local/api/v1/requests/tool \
  -H "X-API-Key: your-snow-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "system.user",
    "content": "Automated laptop refresh notification",
    "tool_id": "snow-integration",
    "trigger_event": "asset.refresh.due"
  }'
```

### Session Management Test
```bash
# Create a session
curl -X POST https://api.selfservice.apps.cluster.local/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test.user",
    "integration_type": "web"
  }'

# Get session info
SESSION_ID="returned-session-id"
curl https://api.selfservice.apps.cluster.local/api/v1/sessions/$SESSION_ID \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

### Common Issues

1. **Pods not starting**:
   ```bash
   # Check pod status
   kubectl get pods -n my-namespace
   
   # Check pod logs
   kubectl logs deployment/self-service-agent-request-manager -n my-namespace
   ```

2. **Knative Eventing not working**:
   ```bash
   # Check Knative Eventing
   kubectl get knativeeventing -n knative-eventing
   
   # Check broker status
   kubectl get broker -n my-namespace
   ```

3. **External access not working**:
   ```bash
   # Check routes
   kubectl get routes -n my-namespace
   
   # Test health endpoint
   curl http://$(kubectl get route self-service-agent-request-manager -n my-namespace -o jsonpath='{.spec.host}')/health
   ```

4. **Database connection issues**:
   ```bash
   # Check PostgreSQL
   kubectl get pods -l app=pgvector -n my-namespace
   kubectl logs -l app=pgvector -n my-namespace
   
   # Test database connection
   kubectl exec -it deployment/pgvector -n my-namespace -- psql -U postgres -d llama_agents -c "SELECT 1;"
   ```

## Monitoring and Observability

### Application Monitoring
```bash
# Check application logs
kubectl logs deployment/self-service-agent-request-manager -n my-namespace
kubectl logs deployment/self-service-agent-agent-service -n my-namespace
kubectl logs deployment/self-service-agent-integration-dispatcher -n my-namespace

# Monitor pod resource usage
kubectl top pods -n my-namespace
```

### Logs
```bash
# Request Manager logs
kubectl logs -l app=self-service-agent-request-manager -n my-namespace

# Agent Service logs
kubectl logs -l app=self-service-agent-agent-service -n my-namespace

# Integration Dispatcher logs
kubectl logs -l app=self-service-agent-integration-dispatcher -n my-namespace
```

This comprehensive deployment guide covers all the major configuration options and operational procedures for the Request Management Layer integration.
