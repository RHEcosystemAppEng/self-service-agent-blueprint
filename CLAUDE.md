# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a self-service agent blueprint implementing a complete AI agent management system with LlamaStack integration, flexible communication modes (Knative eventing, Mock eventing, Direct HTTP), and multi-channel support (Slack, API, CLI). The project consists of:

- **agent-service/**: AI agent processing service that handles LlamaStack interactions
- **request-manager/**: Request routing, session management, and unified communication processing
- **integration-dispatcher/**: Multi-channel delivery (Slack, Email, etc.)
- **asset-manager/**: Agent, knowledge base, and toolgroup registration
- **mcp-servers/**: MCP (Model Context Protocol) servers for external tool integration
- **mock-eventing-service/**: Lightweight mock service for testing without Knative infrastructure
- **shared-models/**: Database models, Pydantic schemas, and Alembic migrations
- **shared-clients/**: Centralized HTTP client libraries for inter-service communication
- **helm/**: Kubernetes Helm charts for OpenShift deployment
- **test/**: Testing utilities and scripts

## Development Commands

### Build System (Makefile)

All development operations use the root Makefile:

```bash
# Install dependencies for all services
make install-all

# Code formatting and linting (entire codebase)
make format  # Run black and isort
make lint    # Run flake8

# Build container images (uses templates)
make build-all-images
make build-request-mgr-image
make build-agent-service-image
make build-integration-dispatcher-image

# Run tests
make test-all
make test-asset-manager
make test-request-manager
```

### Container Operations

The project uses templated Containerfiles for consistency:

```bash
# Build using templates with build args
make build-request-mgr-image    # Uses Containerfile.template
make build-mcp-emp-info-image   # Uses Containerfile.mcp-template

# Push to registry
make push-all-images
```

### Helm Deployment

The system supports three deployment modes:

```bash
# 1. Development Mode (Direct HTTP)
make helm-install-dev NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SLACK_SIGNING_SECRET="your-secret" \
  SNOW_API_KEY="your-key"

# 2. Testing Mode (Mock Eventing)
make helm-install-test NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SLACK_SIGNING_SECRET="your-secret" \
  SNOW_API_KEY="your-key"

# 3. Production Mode (Full Knative Eventing)
make helm-install-prod NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SLACK_SIGNING_SECRET="your-secret" \
  SNOW_API_KEY="your-key"

# Check deployment status
make helm-status NAMESPACE=your-namespace

# Uninstall with cleanup
make helm-uninstall NAMESPACE=your-namespace
```

## Architecture

### Core Components

1. **Agent Service**: Processes AI requests via LlamaStack, handles toolgroups and streaming responses
2. **Request Manager**: Routes requests, manages sessions, unified communication processing with strategy pattern
3. **Integration Dispatcher**: Delivers responses to multiple channels (Slack, Email, etc.)
4. **Asset Manager**: Registers agents, knowledge bases, and toolgroups with LlamaStack
5. **MCP Servers**: External tool integration (employee-info, ServiceNow)
6. **Mock Eventing Service**: Lightweight service that mimics Knative broker behavior for testing
7. **Shared Database**: PostgreSQL with Alembic migrations for session/request persistence

### Communication Architecture

The system supports three communication modes:

#### **1. Development Mode (Direct HTTP)**
- **Direct HTTP Calls**: Services communicate directly via HTTP requests
- **Unified Architecture**: Same core logic with different communication strategy
- **No Eventing Infrastructure**: Minimal dependencies for simple deployments
- **Strategy Pattern**: `CommunicationStrategy` abstraction ensures code consistency

#### **2. Testing Mode (Mock Eventing)**
- **Mock Eventing Service**: Lightweight service that mimics Knative broker behavior
- **Same Request Flow**: API → Request Manager → Agent Service → Integration Dispatcher
- **No Knative Infrastructure**: Perfect for testing and CI/CD without full Knative setup
- **Identical Behavior**: Same event-driven patterns with mock infrastructure

#### **3. Production Mode (Full Knative Eventing)**
- **Knative Eventing**: CloudEvent routing via Kafka brokers and triggers
- **Request Flow**: API → Request Manager → Agent Service → Integration Dispatcher
- **Session Management**: Persistent conversation context across multiple interactions
- **Agent Routing**: Dynamic routing between specialized agents (routing-agent → laptop-refresh)

### Project Structure

- **UV**: Python package management and virtual environments across all services
- **Templated Containerfiles**: `Containerfile.template` and `Containerfile.mcp-template` for consistency
- **Red Hat UBI**: Uses `registry.access.redhat.com/ubi9/python-312-minimal` base images
- **Multi-stage builds**: Optimized Docker layer caching
- **OpenShift**: Helm charts designed for OpenShift with Routes, NetworkPolicies

### Key Environment Variables

- `LLAMA_STACK_URL`: LlamaStack service endpoint (default: http://llamastack:8321)
- `BROKER_URL`: Knative broker endpoint for CloudEvents (or mock eventing service URL)
- `EVENTING_ENABLED`: Boolean flag to enable/disable eventing (true/false)
- `AGENT_SERVICE_URL`: Direct HTTP URL to agent service (only when eventing disabled)
- `INTEGRATION_DISPATCHER_URL`: Direct HTTP URL to integration dispatcher (only when eventing disabled)
- `DATABASE_URL`: PostgreSQL connection string
- `SLACK_SIGNING_SECRET`: Slack webhook verification
- `SNOW_API_KEY`, `HR_API_KEY`: External service API keys

## Code Standards

- Format all Python code with `black`
- Lint with `flake8` 
- Use type hints and docstrings
- Follow PEP 8 guidelines
- Python 3.12+ required

## Local Development

### Testing with LlamaStack

For local testing (see `asset-manager/local_testing/README.md`):

```bash
# 1. Run Ollama server
OLLAMA_HOST=0.0.0.0 ollama serve

# 2. Start LlamaStack container
cd asset-manager/local_testing/
./run_llamastack.sh

# 3. Test agent registration
cd asset-manager/
python -m asset_manager.script.register_assets
```

### Development Workflow

```bash
# 1. Install all dependencies
make install-all

# 2. Run linting and formatting
make lint
make format

# 3. Build and test locally
make build-all-images
make test-all

# 4. Deploy to OpenShift (development mode)
make helm-install-dev NAMESPACE=dev
```

## Documentation

### Architecture Documentation
- **`EVENTING_ALTERNATIVES.md`**: Comprehensive guide to deployment modes and their benefits
- **`COMMUNICATION_MODE_SYNC.md`**: Details on the unified architecture and strategy pattern
- **`REQUEST_MANAGEMENT.md`**: Request processing and session management details
- **`AUTHENTICATION_GUIDE.md`**: Authentication and security configuration
- **`SLACK_INTEGRATION_SETUP.md`**: Slack integration setup and configuration
- **`EMAIL_INTEGRATION_SETUP.md`**: Email integration setup and configuration

### Unified Architecture
The system uses a **Strategy Pattern** to ensure code consistency across communication modes:
- **`CommunicationStrategy`**: Abstract base class for communication mechanisms
- **`EventingStrategy`**: Handles CloudEvent-based communication
- **`DirectHttpStrategy`**: Handles direct HTTP communication
- **`UnifiedRequestProcessor`**: Central request processing logic
- **`UnifiedResponseHandler`**: Central response handling logic

## Dependencies

### Required Cluster Operators
- **Strimzi Kafka Operator**: For Kafka clusters (only for full Knative eventing mode)
- **Knative Eventing**: For CloudEvent routing (only for full Knative eventing mode)

### Optional (disabled by default)
- **Cert-Manager**: Only needed for custom domain certificates (OpenShift Routes provide TLS)

### Multi-Tenant Support
- KnativeKafka resources include release namespace in name
- Multiple deployments in different namespaces supported
- No cluster-wide resource conflicts