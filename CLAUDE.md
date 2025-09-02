# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a self-service agent blueprint implementing a complete AI agent management system with LlamaStack integration, Knative eventing, and multi-channel support (Slack, API, CLI). The project consists of:

- **agent-service/**: AI agent processing service that handles LlamaStack interactions
- **request-manager/**: Request routing, session management, and CloudEvent processing
- **integration-dispatcher/**: Multi-channel delivery (Slack, Email, etc.)
- **asset-manager/**: Agent, knowledge base, and toolgroup registration
- **mcp-servers/**: MCP (Model Context Protocol) servers for external tool integration
- **shared-db/**: Database models and Alembic migrations
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

```bash
# Install with required environment variables
make helm-install NAMESPACE=your-namespace \
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
2. **Request Manager**: Routes requests, manages sessions, handles CloudEvents and agent routing
3. **Integration Dispatcher**: Delivers responses to multiple channels (Slack, Email, etc.)
4. **Asset Manager**: Registers agents, knowledge bases, and toolgroups with LlamaStack
5. **MCP Servers**: External tool integration (employee-info, ServiceNow)
6. **Shared Database**: PostgreSQL with Alembic migrations for session/request persistence

### Event-Driven Architecture

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
- `BROKER_URL`: Knative broker endpoint for CloudEvents
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

# 4. Deploy to OpenShift
make helm-install NAMESPACE=dev
```

## Dependencies

### Required Cluster Operators
- **Strimzi Kafka Operator**: For Kafka clusters
- **Knative Eventing**: For CloudEvent routing

### Optional (disabled by default)
- **Cert-Manager**: Only needed for custom domain certificates (OpenShift Routes provide TLS)

### Multi-Tenant Support
- KnativeKafka resources include release namespace in name
- Multiple deployments in different namespaces supported
- No cluster-wide resource conflicts