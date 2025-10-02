# Self-Service Agent Blueprint

A comprehensive blueprint for building self-service AI agents with modular components including asset management, employee information services, and Helm-based deployment.

## Overview

This is a complete AI agent management system implementing a self-service agent blueprint with LlamaStack integration, flexible communication modes (Knative eventing, Mock eventing, Direct HTTP), and multi-channel support (Slack, API, CLI). The system provides intelligent request routing, session management, and integration delivery across multiple communication channels.

## Project Structure

### Core Services
- **`agent-service/`** - AI agent processing service that handles LlamaStack interactions
- **`request-manager/`** - Request routing, session management, and unified communication processing
- **`integration-dispatcher/`** - Multi-channel delivery (Slack, Email, SMS, Webhooks)
- **`asset-manager/`** - Agent, knowledge base, and toolgroup registration and management
- **`mock-eventing-service/`** - Lightweight mock service for testing without Knative infrastructure

### MCP Servers
- **`mcp-servers/employee-info/`** - Employee information MCP server
- **`mcp-servers/snow/`** - ServiceNow integration MCP server

### Shared Libraries
- **`shared-models/`** - Database models, Pydantic schemas, and Alembic migrations
- **`shared-clients/`** - Centralized HTTP client libraries for inter-service communication

### Infrastructure
- **`helm/`** - Kubernetes Helm charts for OpenShift deployment with Knative configurations
- **`test/`** - Testing utilities and scripts

## Key Features

### Multi-Integration Support
- **Slack**: Full thread and channel support with user context
- **Web**: Browser-based interactions with session management
- **CLI**: Command-line interface integration
- **Tool**: Automated requests from external systems (ServiceNow, HR, etc.)
- **Email**: Email-based interactions and notifications
- **SMS**: SMS notifications and interactions
- **Webhook**: Generic webhook integrations

### Flexible Communication Modes
- **Development Mode**: Direct HTTP communication for local development
- **Testing Mode**: Mock eventing service for CI/CD testing
- **Production Mode**: Full Knative eventing with Kafka for production deployments

### Smart Integration Management
- **Integration Defaults**: Automatic configuration based on system health checks
- **User Overrides**: Custom configurations for specific users
- **Lazy Configuration**: No database entries for users using defaults

### Session Management
- **Persistent Sessions**: Conversation state across interaction turns
- **Integration-Specific Context**: Platform-specific metadata preservation
- **User Context**: User metadata and preferences tracking

## Quick Start

### Prerequisites

- **Python 3.12+** - Required for all services and components
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [Podman](https://podman.io/) or Docker - Container runtime
- [Helm](https://helm.sh/) - Kubernetes package manager (for deployment)
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) - Kubernetes Command line tool

### OpenShift Deployment Prerequisites

For deploying to OpenShift, the following operators are required:

- **OpenShift Serverless Operator** - Required only for production eventing mode (`helm-install-prod`)
- **Streams for Apache Kafka** - Required only for production eventing mode (`helm-install-prod`)

**Note**: Development mode (`helm-install-dev`) and testing mode (`helm-install-test`) do not require these operators.

### Installation

Install all project dependencies:

```bash
make install-all
```

Or install specific components:

```bash
make install                    # Self-service agent dependencies
make install-asset-manager      # Asset manager dependencies
make install-request-manager    # Request manager dependencies
make install-agent-service      # Agent service dependencies
make install-integration-dispatcher  # Integration dispatcher dependencies
make install-mcp-emp-info       # Employee info MCP dependencies
make install-mcp-snow          # ServiceNow MCP dependencies
```

## Development Commands

### Code Quality

```bash
make lint                       # Run flake8 linting on entire codebase
make format                     # Run Black formatting on entire codebase
```

### Testing

```bash
make test-all                   # Run tests for all projects
make test                       # Run tests for self-service agent
make test-asset-manager         # Run tests for asset manager
make test-request-manager       # Run tests for request manager
make test-agent-service         # Run tests for agent service
make test-integration-dispatcher # Run tests for integration dispatcher
make test-mcp-emp-info          # Run tests for employee info MCP
make test-mcp-snow             # Run tests for ServiceNow MCP
```

### Container Operations

> **Note**: Container images do not include HEALTHCHECK instructions as health monitoring is handled by Kubernetes liveness and readiness probes in the Helm deployment.

#### Building Images

```bash
make build-all-images           # Build all container images
make build-agent-image          # Build self-service agent image
make build-asset-mgr-image      # Build asset manager image
make build-request-mgr-image    # Build request manager image
make build-agent-service-image  # Build agent service image
make build-integration-dispatcher-image  # Build integration dispatcher image
make build-mcp-emp-info-image   # Build employee info MCP image
make build-mcp-snow-image       # Build ServiceNow MCP image
```

If you need to build images for ARM architecture, try:
```bash
make build-all-images REGISTRY=quay.io/<user> ARCH="linux/arm64"
```
In this case you also speficy to use some registry (not mandatory).

#### Pushing Images

```bash
make push-all-images            # Push all images to registry
make push-agent-image           # Push self-service agent image
make push-asset-mgr-image       # Push asset manager image
make push-request-mgr-image     # Push request manager image
make push-agent-service-image   # Push agent service image
make push-integration-dispatcher-image  # Push integration dispatcher image
make push-mcp-emp-info-image    # Push employee info MCP image
make push-mcp-snow-image        # Push ServiceNow MCP image
```

## Deployment

### Helm Operations

```bash
make helm-depend                # Update Helm dependencies
make helm-list-models           # List available models
```

### Deploy to Kubernetes/OpenShift

The blueprint supports three deployment modes:

- **Development Mode** (`helm-install-dev`): Direct HTTP communication for local development and CLI tools
- **Testing Mode** (`helm-install-test`): Mock eventing service for CI/CD and integration testing
- **Production Mode** (`helm-install-prod`): Full Knative eventing with Kafka for production deployments

```bash
# Set your namespace
export NAMESPACE=your-namespace

# Install with direct HTTP communication (development mode)
make helm-install-dev

# Install with mock eventing service (testing/CI mode)
make helm-install-test

# Install with full Knative eventing (production mode)
make helm-install-prod

# Check deployment status
make helm-status

# Uninstall
make helm-uninstall
```

## Configuration

### Container Registry

By default, images are built for `quay.io/ecosystem-appeng`. To use a different registry:

```bash
export REGISTRY=your-registry.com/your-org
make build-all-images
```

### Version Management

To build with a specific version:

```bash
export VERSION=1.0.0
make build-all-images
```

## Available Make Targets

Run `make help` to see all available commands with descriptions. Key deployment targets include:

- `helm-install-dev` - Install with direct HTTP communication (development)
- `helm-install-test` - Install with mock eventing service (testing/CI)
- `helm-install-prod` - Install with full Knative eventing (production)

## Documentation

### Core Documentation
- [Integration Guide](INTEGRATION_GUIDE.md) - Complete integration and request management guide
- [API Reference](API_REFERENCE.md) - Complete API documentation and endpoints
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - System architecture and flow diagrams
- [Authentication Guide](AUTHENTICATION_GUIDE.md) - Authentication setup and configuration

### Integration Guides
- [Slack Setup](SLACK_SETUP.md) - Slack integration configuration
- [Tool Integration Guide](TOOL_INTEGRATION_GUIDE.md) - Tool integration patterns

### Component Documentation
- [Asset Manager](asset-manager/README.md) - Detailed asset manager documentation
- [Employee Info MCP](mcp-servers/employee-info/README.md) - Employee information service documentation
- [ServiceNow MCP](mcp-servers/snow/README.md) - ServiceNow integration documentation

## Local Deployment with Kind cluster

It is possible to run a local Kubernetes cluster with a container used as registry, running the script:

```bash
sh ./scripts/ci/kind-with-registry.sh
```

When a cluster is disposed using the command:

```bash
kind delete cluster
```

The images will be cached on the registry container.

## System Architecture

The system consists of three main services working together:

### Request Manager
- **Normalizes** incoming requests from different integration types
- **Manages sessions** using PostgreSQL as a key-value store
- **Routes requests** to appropriate agents (via HTTP or CloudEvents)
- **Tracks conversation state** and request history
- **Returns responses** directly to Web/CLI/Tool/Generic integrations
- **Forwards responses** to Integration Dispatcher for delivery to Slack/Email/Webhook/Test integrations

### Agent Service
- **Processes normalized requests** from the Request Manager
- **Integrates with Llama Stack** for agent interactions
- **Manages agent sessions** and conversation context
- **Publishes responses** to the broker via CloudEvents for delivery to users

### Integration Dispatcher
- **Handles response delivery** to external integrations
- **Multi-tenant delivery** to Slack, Email, SMS, Webhooks
- **Manages delivery status** and retry logic
- **Supports various integration protocols**
- **Manages integration defaults** and user overrides

## Shared Libraries

The system uses two key shared libraries:

### shared-models
- Database models and schemas
- Pydantic models for API communication
- Alembic migrations
- CloudEvent utilities
- FastAPI utilities
- Health checkers
- Logging utilities

### shared-clients
- HTTP client implementations
- Service communication utilities
- Request manager client
- Agent service client
- Stream processor

## Integration Types

### Bidirectional Integrations (Request + Response Delivery)
- **Slack**: Receives requests via Integration Dispatcher, responses delivered via Slack API

### Request-Only Integrations (Direct Response)
- **Web**: Receives requests directly via web interface, responses returned directly
- **CLI**: Receives requests directly, responses handled synchronously by CLI tool
- **Tool**: Receives requests directly, responses returned immediately (notification-based)
- **Generic**: Receives requests directly, responses returned directly (synchronous)

### Response-Only Integrations (No Incoming Requests)
- **Email**: Only delivers responses via SMTP (no incoming email requests)
- **SMS**: Only delivers responses via SMS (no incoming SMS requests)
- **Webhook**: Only delivers responses via HTTP POST (no incoming webhook requests)
- **Test**: Only delivers responses for testing (no incoming test requests)

## Related Documentation

- [CLAUDE.md](CLAUDE.md) - Development guidance for Claude Code
- [GUIDELINES.md](GUIDELINES.md) - Code practices and project structure guidelines

# Test