# Eventing Alternatives for Testing and CI

This document describes the different options available for deploying the self-service agent stack without requiring full Knative eventing infrastructure, which is useful for testing, CI/CD, and development environments.

## Overview

The self-service agent stack uses Knative eventing for event-driven communication between services:
- **Request Manager** → **Agent Service**: Request processing
- **Agent Service** → **Integration Dispatcher**: Response delivery
- **Agent Service** → **Request Manager**: Sync API support
- **Request Manager** → **Integration Dispatcher**: Notifications

## Deployment Options

### Option 1: Full Knative Eventing (Production)

This is the default and recommended approach for production deployments.

```bash
# Deploy with full Knative eventing
helm install self-service-agent ./helm \
  --set requestManagement.knative.eventing.enabled=true \
  --set requestManagement.knative.kafka.enabled=true \
  --set requestManagement.kafka.enabled=true
```

**Requirements:**
- OpenShift Serverless Operator
- Streams for Apache Kafka Operator
- Kafka cluster

### Option 2: Mock Eventing Service (Testing/CI)

A lightweight mock service that simulates Knative broker behavior without requiring the full eventing infrastructure.

```bash
# Deploy with mock eventing service
helm install self-service-agent ./helm \
  --set requestManagement.knative.eventing.enabled=false \
  --set requestManagement.knative.mockEventing.enabled=true \
  --set requestManagement.kafka.enabled=false
```

**Benefits:**
- No external dependencies (Kafka, Knative)
- Fast startup and teardown
- Perfect for testing and CI
- Simulates real eventing behavior

**Limitations:**
- Events are not persisted
- No guaranteed delivery
- Single instance only

### Option 3: Direct HTTP Communication (Development)

Services communicate directly via HTTP calls instead of events.

```bash
# Deploy with direct HTTP communication
helm install self-service-agent ./helm \
  --set requestManagement.knative.eventing.enabled=false \
  --set requestManagement.knative.mockEventing.enabled=false \
  --set requestManagement.kafka.enabled=false
```

**Benefits:**
- Simplest deployment
- No additional services required
- Good for development and debugging

**Limitations:**
- Synchronous communication only
- No event replay capabilities
- Limited scalability

## Configuration Details

### Mock Eventing Service

The mock eventing service provides:

- **Broker Endpoint**: `/namespace/broker-name` - Accepts CloudEvents
- **Subscription Management**: `/subscriptions` - Configure event routing
- **Event History**: `/events` - View processed events
- **Health Check**: `/health` - Service health status

**Environment Variables:**
```yaml
PORT: 8080
HOST: 0.0.0.0
LOG_LEVEL: INFO
```

**Resource Requirements:**
```yaml
resources:
  requests:
    memory: 128Mi
    cpu: 100m
  limits:
    memory: 256Mi
    cpu: 200m
```

### Direct HTTP Mode

When eventing is disabled, services use direct HTTP communication:

- **Request Manager** → **Agent Service**: `POST /process`
- **Agent Service** → **Integration Dispatcher**: `POST /deliver`
- **Request Manager** → **Integration Dispatcher**: `POST /notifications`

## Deployment Examples

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
- name: Deploy with Mock Eventing
  run: |
    helm install test-stack ./helm \
      --set requestManagement.knative.eventing.enabled=false \
      --set requestManagement.knative.mockEventing.enabled=true \
      --set requestManagement.kafka.enabled=false \
      --wait --timeout=5m

- name: Run Tests
  run: |
    # Run your integration tests here
    pytest tests/

- name: Cleanup
  run: |
    helm uninstall test-stack
```

### Local Development

```bash
# Quick local deployment without eventing
helm install dev-stack ./helm \
  --set requestManagement.knative.eventing.enabled=false \
  --set requestManagement.knative.mockEventing.enabled=true \
  --set requestManagement.kafka.enabled=false \
  --set requestManagement.externalAccess.enabled=false
```

### Testing Different Scenarios

```bash
# Test with mock eventing
helm install test-mock ./helm \
  --set requestManagement.knative.eventing.enabled=false \
  --set requestManagement.knative.mockEventing.enabled=true

# Test with direct HTTP
helm install test-direct ./helm \
  --set requestManagement.knative.eventing.enabled=false \
  --set requestManagement.knative.mockEventing.enabled=false

# Test with full eventing
helm install test-full ./helm \
  --set requestManagement.knative.eventing.enabled=true
```

## Monitoring and Debugging

### Mock Eventing Service

```bash
# Check service health
kubectl port-forward svc/self-service-agent-mock-eventing 8080:8080
curl http://localhost:8080/health

# View event subscriptions
curl http://localhost:8080/subscriptions

# View recent events
curl http://localhost:8080/events

# Clear event history
curl -X DELETE http://localhost:8080/events
```

### Service Logs

```bash
# Check request manager logs
kubectl logs -f deployment/self-service-agent-request-manager

# Check agent service logs
kubectl logs -f deployment/self-service-agent-agent-service

# Check integration dispatcher logs
kubectl logs -f deployment/self-service-agent-integration-dispatcher

# Check mock eventing service logs
kubectl logs -f deployment/self-service-agent-mock-eventing
```

## Migration Between Modes

### From Mock to Full Eventing

1. Deploy with full eventing enabled
2. Verify services are healthy
3. Remove mock eventing service

```bash
helm upgrade self-service-agent ./helm \
  --set requestManagement.knative.eventing.enabled=true \
  --set requestManagement.knative.mockEventing.enabled=false
```

### From Direct HTTP to Eventing

1. Deploy mock eventing service
2. Verify event routing works
3. Switch to full eventing if needed

## Troubleshooting

### Common Issues

**Services fail to start with "BROKER_URL required" error:**
- Ensure `EVENTING_ENABLED=false` is set when using direct HTTP mode
- Check that mock eventing service is running when using mock mode

**Events not being delivered:**
- Check mock eventing service subscriptions: `curl http://localhost:8080/subscriptions`
- Verify service URLs in subscriptions are correct
- Check service logs for delivery errors

**Timeout errors in direct HTTP mode:**
- Increase timeout values in service configurations
- Check network connectivity between services
- Verify service health endpoints

### Debug Commands

```bash
# Check all pods
kubectl get pods -l app.kubernetes.io/name=self-service-agent

# Check services
kubectl get svc -l app.kubernetes.io/name=self-service-agent

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp

# Port forward for debugging
kubectl port-forward svc/self-service-agent-request-manager 8080:8080
kubectl port-forward svc/self-service-agent-mock-eventing 8081:8080
```

## Performance Considerations

### Mock Eventing Service
- **Memory**: ~50MB baseline, +1MB per 1000 events
- **CPU**: Minimal, only during event processing
- **Storage**: In-memory only, events lost on restart

### Direct HTTP Mode
- **Latency**: Lower (no event routing overhead)
- **Throughput**: Limited by HTTP connection pools
- **Reliability**: No retry mechanisms

### Full Eventing
- **Latency**: Higher (event routing + Kafka)
- **Throughput**: High (Kafka scaling)
- **Reliability**: High (persistent events, retries)

## Best Practices

1. **Use mock eventing for CI/CD** - Fast, reliable, no external dependencies
2. **Use direct HTTP for development** - Simplest setup, easy debugging
3. **Use full eventing for production** - Scalable, reliable, persistent
4. **Test all modes** - Ensure your application works in all configurations
5. **Monitor resource usage** - Each mode has different resource requirements

## Future Enhancements

- **Redis-based mock eventing** - Persistent events, multiple instances
- **Message queue fallback** - RabbitMQ, NATS support
- **Hybrid mode** - Eventing for critical paths, direct HTTP for others
- **Auto-detection** - Automatically choose best mode based on environment
