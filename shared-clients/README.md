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
        endpoint="generic/sync"
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

## Installation

This package is designed to be used as a local dependency within the self-service agent blueprint project.

```bash
# Install in development mode
cd shared-clients
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Environment Variables

- `REQUEST_MANAGER_URL`: URL of the Request Manager service (default: http://localhost:8080)
- `AGENT_MESSAGE_TERMINATOR`: Message terminator for agent responses (optional)

## Development

```bash
# Format code
black .
isort .

# Lint code
flake8 .

# Run tests
pytest
```
