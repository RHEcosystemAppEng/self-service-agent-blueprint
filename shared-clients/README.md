# Shared Clients

This package provides reusable client libraries for interacting with the self-service agent blueprint components.

## Components

### RequestManagerClient

Base client for interacting with the Request Manager service. Provides methods for:

- Sending requests to various endpoints
- Getting request status
- Updating sessions
- Managing HTTP connections

### CLIChatClient

CLI-specific chat client that extends RequestManagerClient with:

- Interactive chat loop functionality
- Session management
- Command context handling
- Debug output support

### ServiceClient

Base HTTP client for service-to-service communication with:

- HTTP/2 support for better performance
- Connection pooling and keepalive
- Compression support (gzip, deflate, br)
- Standard REST methods (GET, POST, PUT, DELETE)
- Streaming support for Server-Sent Events

### AgentServiceClient

Specialized client for the Agent Service with:

- Request processing methods
- Streaming response support
- Default configuration for Agent Service URL

### IntegrationDispatcherClient

Client for the Integration Dispatcher service with:

- Delivery request methods
- Integration-specific operations
- Default configuration for Integration Dispatcher URL

### LlamaStackStreamProcessor

Unified stream processor for LlamaStack streaming responses with:

- Token usage extraction
- Content streaming with callbacks
- Error handling
- Tool call processing

## Usage

### Basic Request Manager Client

```python
from shared_clients import RequestManagerClient

async def main():
    client = RequestManagerClient(
        request_manager_url="http://localhost:8080",
        user_id="user123"
    )

    response = await client.send_request(
        content="Hello, agent!",
        integration_type="CLI",
        endpoint="generic"
    )

    print(response)
    await client.close()
```

### CLI Chat Client

```python
from shared_clients import CLIChatClient

async def main():
    client = CLIChatClient(
        request_manager_url="http://localhost:8080"
    )

    # Run interactive chat
    await client.chat_loop(
        initial_message="please introduce yourself and tell me how you can help"
    )
```

### Programmatic Usage

```python
from shared_clients import CLIChatClient

async def main():
    client = CLIChatClient()

    # Send individual messages
    response1 = await client.send_message("Hello!")
    print(f"Agent: {response1}")

    response2 = await client.send_message("How can you help me?")
    print(f"Agent: {response2}")

    # Reset session
    await client.reset_session()

    await client.close()
```

### Service-to-Service Communication

```python
from shared_clients import AgentServiceClient

async def main():
    # Using default Agent Service URL from environment
    client = AgentServiceClient()

    # Or specify custom URL
    # client = AgentServiceClient(base_url="http://custom-agent-service:80")

    response = await client.process_request({
        "user_id": "user123",
        "content": "Process this request",
        "integration_type": "WEB"
    })

    print(response)
    await client.close()
```

### Using Helper Functions

```python
from shared_clients import (
    initialize_service_clients,
    get_agent_client,
    get_integration_dispatcher_client,
    cleanup_service_clients
)

# Initialize all service clients with custom URLs
initialize_service_clients(
    agent_service_url="http://agent-service:80",
    integration_dispatcher_url="http://integration-dispatcher:80"
)

# Get clients
agent_client = get_agent_client()
dispatcher_client = get_integration_dispatcher_client()

# Use clients...
response = await agent_client.process_request(data)

# Clean up when done
await cleanup_service_clients()
```

### Stream Processing

```python
from shared_clients import LlamaStackStreamProcessor

async def process_streaming_response(response_stream):
    result = await LlamaStackStreamProcessor.process_stream(
        response_stream=response_stream,
        on_content=lambda content: print(content, end="", flush=True),
        on_error=lambda error: print(f"Error: {error}"),
        collect_content=True
    )

    print(f"\nTotal tokens: {result['total_tokens']}")
    print(f"Full content: {result['content']}")
```

## Installation

This package is designed to be used as a local dependency within the self-service agent blueprint project.

```bash
# From the project root, install all dependencies
make install-all

# Or install just shared-clients
cd shared-clients
uv sync

# Install with dev dependencies
uv sync --group dev
```

## Environment Variables

### Request Manager Client
- `REQUEST_MANAGER_URL`: URL of the Request Manager service (default: `http://localhost:8080`)
- `AGENT_MESSAGE_TERMINATOR`: Message terminator for agent responses (optional)

### Service Clients
- `AGENT_SERVICE_URL`: URL of the Agent Service (default: `http://self-service-agent-agent-service:80`)
- `INTEGRATION_DISPATCHER_URL`: URL of the Integration Dispatcher (default: `http://self-service-agent-integration-dispatcher:80`)

## Development

### Run Tests
```bash
# From project root
make test-shared-clients

# Or directly
cd shared-clients
uv run pytest
```

### Format Code
```bash
# From project root
make format

# Or directly
cd shared-clients
uv run black .
uv run isort .
```

### Lint Code
```bash
# From project root
make lint

# Or directly
cd shared-clients
uv run flake8 .
uv run mypy src/
```

## Exported Classes and Functions

### Main Clients
- `RequestManagerClient` - Base client for Request Manager
- `CLIChatClient` - CLI chat interface
- `ServiceClient` - Base HTTP client
- `AgentServiceClient` - Agent Service client
- `IntegrationDispatcherClient` - Integration Dispatcher client

### Helper Functions
- `initialize_service_clients()` - Initialize all service clients
- `cleanup_service_clients()` - Clean up all service clients
- `get_agent_client()` - Get Agent Service client instance
- `get_request_manager_client()` - Get Request Manager client instance
- `get_integration_dispatcher_client()` - Get Integration Dispatcher client instance

### Utilities
- `LlamaStackStreamProcessor` - Stream processing for LlamaStack responses
