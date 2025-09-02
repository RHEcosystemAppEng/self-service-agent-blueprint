# Request Management Layer

The Request Management Layer provides a centralized system for handling requests from various integrations (Slack, Web, CLI, Tools) and managing conversation sessions with AI agents. It uses an event-driven architecture with OpenShift Serverless (Knative) and CloudEvents for scalable, loosely-coupled communication.

## Architecture

```
[ External Integrations (Slack/Web/CLI/Tool) ]
              │
      [ API Gateway (3scale/Kong/OAuth) ]
              │
              ▼
      [ Knative Broker/Trigger ]
              │
              ▼
      [ Request Manager (Knative Service) ]
              │
      ┌───────┴─────────┐
      │                 │
 [ Postgres KV Store ]  [ Broker → Agent Service ]
      │                 │
      └───────◄─────────┘
```

## Components

### Request Manager Service

A FastAPI-based Knative service that:

- **Normalizes incoming requests** from different integrations into a common format
- **Manages sessions** using PostgreSQL as a key-value store
- **Routes requests** to appropriate agents via CloudEvents
- **Tracks conversation state** and request history
- **Handles responses** from agents and forwards them back to integrations

### Agent Service

A CloudEvent-driven service that:

- **Processes normalized requests** from the Request Manager
- **Integrates with Llama Stack** for agent interactions
- **Manages agent sessions** and conversation context  
- **Publishes responses** back to the Request Manager via CloudEvents

### Database Schema

The system uses the existing `llama_agents` PostgreSQL database with these tables:

- `request_sessions`: Session management and conversation state
- `request_logs`: Individual request/response tracking
- `integration_configs`: Configuration for different integrations

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

1. **Request Received**: Integration sends request to Request Manager
2. **Session Management**: Request Manager finds/creates session in PostgreSQL
3. **Request Normalization**: Convert integration-specific request to common format
4. **Event Publishing**: Publish CloudEvent to Knative Broker
5. **Agent Processing**: Agent Service receives event and processes with Llama Stack
6. **Response Publishing**: Agent Service publishes response CloudEvent
7. **Response Handling**: Request Manager receives response and forwards to integration

## CloudEvent Types

- `com.self-service-agent.request.created`: New request from integration
- `com.self-service-agent.agent.response-ready`: Agent response available
- `com.self-service-agent.session.created`: New session created
- `com.self-service-agent.session.updated`: Session state updated

## Development

### Prerequisites

- Python 3.11+
- uv package manager
- PostgreSQL (for local development)
- OpenShift Serverless (for production)

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
```

### Deployment

The services are deployed as Knative Services with the following configurations:

- **Request Manager**: Handles HTTP requests from integrations
- **Agent Service**: Processes CloudEvents from the broker
- **Knative Broker**: Routes events between services
- **Triggers**: Filter and route specific event types

Deploy using Helm (includes all Knative and Service Mesh configurations):

```bash
make helm-install
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
- `LOG_LEVEL`: Logging level (default: INFO)

#### Agent Service
- `LLAMA_STACK_URL`: Llama Stack service URL (default: http://llamastack:8321)
- `BROKER_URL`: Knative Broker URL
- `DEFAULT_AGENT_ID`: Default agent for routing (default: routing-agent)
- `AGENT_TIMEOUT`: Agent response timeout in seconds (default: 120)

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
