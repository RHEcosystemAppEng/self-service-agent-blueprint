# Request Management Layer

The Request Management Layer provides a centralized system for handling requests from various integrations (Slack, Web, CLI, Tools) and managing conversation sessions with AI agents. It uses an event-driven architecture with OpenShift Serverless (Knative) and CloudEvents for scalable, loosely-coupled communication.

## Architecture

For detailed architecture diagrams and flow descriptions, see the main [Architecture Documentation](../ARCHITECTURE_DIAGRAMS.md).

The Request Manager is part of a larger system that includes:
- **Integration Dispatcher**: Handles Slack requests and response delivery
- **Request Manager**: Processes requests from Web/CLI/Tool integrations and manages sessions
- **Agent Service**: Processes requests with LlamaStack and generates responses
- **Database**: Stores session and request data

## Integration Types and Response Patterns

### Bidirectional Integrations (Request + Response Delivery)
- **Slack**: Receives requests via Integration Dispatcher, responses delivered via Slack API

### Request-Only Integrations (Direct Response)
- **Web**: Receives requests directly via web interface, responses returned directly
- **CLI**: Receives requests directly, responses handled synchronously by CLI tool
- **Tool**: Receives requests directly, responses returned immediately (notification-based)
- **Generic**: Receives requests directly, responses returned directly (async or sync)

### Response-Only Integrations (No Incoming Requests)
- **Email**: Only delivers responses via SMTP (no incoming email requests)
- **SMS**: Only delivers responses via SMS (no incoming SMS requests)
- **Webhook**: Only delivers responses via HTTP POST (no incoming webhook requests)
- **Test**: Only delivers responses for testing (no incoming test requests)

## Components

### Request Manager Service

A FastAPI-based Knative service that:

- **Normalizes incoming requests** from different integrations into a common format
- **Manages request sessions** using PostgreSQL as a key-value store (separate from LlamaStack agent sessions)
- **Routes requests** to appropriate agents via CloudEvents
- **Tracks conversation state** and request history
- **Returns responses** directly to Web/CLI/Tool/Generic integrations (synchronous HTTP responses)
- **Forwards responses** to Integration Dispatcher for delivery to Slack/Email/Webhook/Test integrations

### Agent Service

A CloudEvent-driven service that:

- **Processes normalized requests** from the Request Manager
- **Integrates with Llama Stack** for agent interactions
- **Manages agent sessions** and conversation context  
- **Publishes responses** to the broker via CloudEvents for delivery to users

### Database Schema

The system uses the existing `llama_agents` PostgreSQL database with these tables:

- `request_sessions`: Session management and conversation state
- `request_logs`: Individual request/response tracking
- `user_integration_configs`: Per-user integration configuration overrides
- `integration_default_configs`: Default integration configurations for new users

## Integration Types

### Slack Integration
```python
POST /api/v1/requests/slack
{
    "user_id": "user123",
    "content": "I need help with my laptop",
    "channel_id": "C123456789",
    "thread_id": "1234567890.123456",
    "slack_user_id": "U123456789",
    "slack_team_id": "T123456789"
}
```

### Web Integration
```python
POST /api/v1/requests/web
{
    "user_id": "webuser123", 
    "content": "I want to refresh my laptop",
    "session_token": "token123",
    "client_ip": "192.168.1.1",
    "user_agent": "Mozilla/5.0..."
}
```

### CLI Integration
```python
POST /api/v1/requests/cli
{
    "user_id": "cliuser123",
    "content": "help me with laptop refresh",
    "cli_session_id": "cli-session-456",
    "command_context": {"command": "agent", "args": ["help"]}
}
```

### Tool Integration
```python
POST /api/v1/requests/tool
{
    "user_id": "tooluser123",
    "content": "User laptop needs refresh - system notification",
    "tool_id": "snow-integration",
    "tool_instance_id": "instance-789", 
    "trigger_event": "laptop.refresh.required",
    "tool_context": {"ticket_id": "INC123456", "priority": "high"}
}
```

## Event Flow

### For Slack Integration (Bidirectional):
1. **Request Received**: Slack sends request to Integration Dispatcher
2. **Request Forwarding**: Integration Dispatcher forwards to Request Manager
3. **Session Management**: Request Manager finds/creates session in PostgreSQL
4. **Request Normalization**: Convert integration-specific request to common format
5. **Event Publishing**: Publish CloudEvent to Knative Broker
6. **Agent Processing**: Agent Service receives event and processes with Llama Stack
7. **Response Publishing**: Agent Service publishes response CloudEvent
8. **Response Delivery**: Integration Dispatcher receives response and delivers to Slack

### For Web/CLI/Tool Integration (Request-Only):
1. **Request Received**: Web/CLI/Tool sends request directly to Request Manager
2. **Session Management**: Request Manager finds/creates session in PostgreSQL
3. **Request Normalization**: Convert integration-specific request to common format
4. **Event Publishing**: Publish CloudEvent to Knative Broker
5. **Agent Processing**: Agent Service receives event and processes with Llama Stack
6. **Response Publishing**: Agent Service publishes response CloudEvent
7. **Response Handling**: Web/CLI/Tool receives response directly (no Integration Dispatcher)

### For Email/Webhook/Test Integration (Response-Only):
1. **Request Received**: User sends request via Slack/Web/CLI/Tool (not via Email/Webhook/Test)
2. **Session Management**: Request Manager finds/creates session in PostgreSQL
3. **Request Normalization**: Convert integration-specific request to common format
4. **Event Publishing**: Publish CloudEvent to Knative Broker
5. **Agent Processing**: Agent Service receives event and processes with Llama Stack
6. **Response Publishing**: Agent Service publishes response CloudEvent
7. **Response Delivery**: Integration Dispatcher delivers response via Email/Webhook/Test

## CloudEvent Types

### Request Events
- `com.self-service-agent.request.created`: New request from integration
- `com.self-service-agent.request.processing`: Request being processed by agent

### Response Events
- `com.self-service-agent.agent.response-ready`: Agent response ready for delivery

### Database Update Events
- `com.self-service-agent.request.database-update`: Database update requested

## Development

### Prerequisites

- **Python 3.12+** - Required for all services and components
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [Podman](https://podman.io/) or Docker - Container runtime (for building images)
- [Helm](https://helm.sh/) - Kubernetes package manager (for deployment)
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) - Kubernetes command line tool
- PostgreSQL (for local development)
- OpenShift Serverless (for production deployment)

### Local Development

1. Install dependencies:
```bash
cd request-manager
uv sync
```

2. Set environment variables:
```bash
export POSTGRES_HOST=localhost
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=password
export POSTGRES_DB=llama_agents
export BROKER_URL=http://localhost:8080  # For local testing
```

3. Run the service:
```bash
uv run python -m uvicorn request_manager.main:app --reload
```

4. Run tests:
```bash
uv run python -m pytest tests/
```

### Building Container

```bash
# From project root
make build-request-mgr-image
make build-agent-service-image
make build-integration-dispatcher-image
```

### Deployment

The services are deployed as Knative Services with the following configurations:

- **Request Manager**: Handles HTTP requests from integrations
- **Agent Service**: Processes CloudEvents from the broker
- **Knative Broker**: Routes events between services
- **Triggers**: Filter and route specific event types

Deploy using Helm (includes all Knative configurations):

```bash
# Development mode (direct HTTP communication)
make helm-install-dev NAMESPACE=your-namespace

# Testing mode (mock eventing service)
make helm-install-test NAMESPACE=your-namespace

# Production mode (full Knative eventing)
make helm-install-prod NAMESPACE=your-namespace
```

## Configuration

### Environment Variables

#### Request Manager
- `POSTGRES_HOST`: PostgreSQL host (default: pgvector)
- `POSTGRES_PORT`: PostgreSQL port (default: 5432)
- `POSTGRES_DB`: Database name (default: llama_agents)
- `POSTGRES_USER`: Database user
- `POSTGRES_PASSWORD`: Database password
- `BROKER_URL`: Knative Broker URL
- `EVENTING_ENABLED`: Enable/disable eventing (default: true)
- `EVENT_MAX_RETRIES`: Maximum event retry attempts (default: 3)
- `LOG_LEVEL`: Logging level (default: INFO)
- `JWT_ENABLED`: Enable JWT authentication (default: false)
- `JWT_SECRET_KEY`: JWT secret key for token validation
- `API_KEYS_ENABLED`: Enable API key authentication (default: false)
- `SLACK_SIGNING_SECRET`: Slack signing secret for request verification
- `SNOW_API_KEY`: ServiceNow integration API key
- `HR_API_KEY`: HR system integration API key
- `MONITORING_API_KEY`: Monitoring system API key

#### Agent Service
- `LLAMA_STACK_URL`: Llama Stack service URL (default: http://llamastack:8321)
- `BROKER_URL`: Knative Broker URL
- `DEFAULT_AGENT_ID`: Default agent for routing (configurable via Helm values, default: routing-agent)
- `AGENT_TIMEOUT`: Agent response timeout in seconds (configurable via Helm values, default: 120)

## Monitoring

### Health Checks

- Request Manager: `GET /health`
- Agent Service: `GET /health`

### Metrics

The services expose metrics for:
- Request processing time
- Session creation/updates
- Event publishing success/failure
- Database connection health

### Logging

Structured JSON logging is used throughout, with correlation IDs for tracing requests across services.

## Security

- All services run as non-root users
- Database credentials are stored in Kubernetes secrets
- API endpoints support authentication via API Gateway
- Network policies restrict inter-service communication

## Scaling

- **Request Manager**: Auto-scales based on HTTP request load
- **Agent Service**: Auto-scales based on CloudEvent processing
- **Database**: Uses connection pooling for efficient resource usage
- **Event System**: Kafka backend provides high throughput and reliability
