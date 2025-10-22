# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a self-service agent blueprint implementing a complete AI agent management system with LlamaStack integration, flexible communication modes (Knative eventing, Mock eventing, Direct HTTP), and multi-channel support (Slack, API, CLI). The project consists of:

- **agent-service/**: AI agent processing service that handles LlamaStack interactions
- **request-manager/**: Request routing, session management, and unified communication processing
- **integration-dispatcher/**: Multi-channel delivery (Slack, Email, etc.)
- **asset-manager/**: Agent and knowledge base registration
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

1. **Agent Service**: Processes AI requests via LlamaStack, handles streaming responses
2. **Request Manager**: Routes requests, manages sessions, unified communication processing with strategy pattern
3. **Integration Dispatcher**: Delivers responses to multiple channels (Slack, Email, etc.)
4. **Asset Manager**: Registers knowledge bases with LlamaStack; MCP servers configured in agent YAML files
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

### Integration Defaults System

The system uses an **Integration Defaults** approach with **User Overrides** to provide smart defaults for all users while allowing customization when needed:

- **Smart Defaults**: Automatic configuration based on system health checks
- **User Overrides**: Custom configurations for specific users
- **Lazy Configuration**: No database entries for users using defaults
- **Priority-based Delivery**: Delivers through highest priority channels first

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

# 3. Test asset registration (knowledge bases)
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

### Core Documentation
- **`API_REFERENCE.md`**: Complete API documentation and endpoints
- **`INTEGRATION_GUIDE.md`**: Complete integration and request management guide
- **`ARCHITECTURE_DIAGRAMS.md`**: System architecture and flow diagrams
- **`AUTHENTICATION_GUIDE.md`**: Enhanced security and authentication setup with production readiness warnings
- **`SLACK_SETUP.md`**: Slack app configuration guide
- **`TOOL_INTEGRATION_GUIDE.md`**: Tool integration patterns

### Component Documentation
- **`asset-manager/README.md`**: Asset manager service documentation
- **`mcp-servers/employee-info/README.md`**: Employee information service documentation
- **`mcp-servers/snow/README.md`**: ServiceNow integration documentation

### Unified Architecture
The system uses a **Strategy Pattern** to ensure code consistency across communication modes:
- **`CommunicationStrategy`**: Abstract base class for communication mechanisms
- **`EventingStrategy`**: Handles CloudEvent-based communication
- **`DirectHttpStrategy`**: Handles direct HTTP communication
- **`UnifiedRequestProcessor`**: Central request processing logic
- **`UnifiedResponseHandler`**: Central response handling logic

## Security & Authentication

### Production Ready Authentication
- **API Key Authentication**: Simple key-based authentication (recommended)
- **Slack Signature Verification**: Webhook requests verified using Slack signing secret
- **Legacy Header Authentication**: Support for existing authentication systems

### Not Production Ready
- **JWT Authentication**: JWT parsing exists but **signature verification is not implemented** (TODO in code). **Not production-ready**.

## Dependencies

### Required Cluster Operators
- **OpenShift Serverless Operator**: For Knative eventing (production mode only)
- **Streams for Apache Kafka**: For Kafka clusters (production mode only)

### Optional (disabled by default)
- **Cert-Manager**: Only needed for custom domain certificates (OpenShift Routes provide TLS)

### Multi-Tenant Support
- KnativeKafka resources include release namespace in name
- Multiple deployments in different namespaces supported
- No cluster-wide resource conflicts

## Key Features

### Multi-Integration Support
- **Slack**: Full thread and channel support with user context
- **Web**: Browser-based interactions with session management
- **CLI**: Command-line interface integration
- **Tool**: Automated requests from external systems (ServiceNow, HR, etc.)
- **Email**: Email-based interactions and notifications
- **SMS**: SMS notifications and interactions
- **Webhook**: Generic webhook integrations

### Smart Integration Management
- **Integration Defaults**: Automatic configuration based on system health checks
- **User Overrides**: Custom configurations for specific users
- **Lazy Configuration**: No database entries for users using defaults

### Session Management
- **Persistent Sessions**: Conversation state across interaction turns
- **Integration-Specific Context**: Platform-specific metadata preservation
- **User Context**: User metadata and preferences tracking

## Related Documentation

- [README.md](README.md) - Main project documentation
- [GUIDELINES.md](GUIDELINES.md) - Code practices and project structure guidelines