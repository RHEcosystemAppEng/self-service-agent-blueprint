# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a self-service agent blueprint implementing a complete AI agent management system with LlamaStack integration, eventing-based communication (Knative eventing or Mock eventing), and multi-channel support (Slack, API, CLI). The project consists of:

- **agent-service/**: AI agent processing service with knowledge base management, session management, and LangGraph state machine
- **request-manager/**: Request routing, normalization, and unified communication processing
- **integration-dispatcher/**: Multi-channel delivery (Slack, Email, etc.)
- **mcp-servers/**: MCP (Model Context Protocol) servers for external tool integration
- **mock-eventing-service/**: Lightweight mock service for testing without Knative infrastructure
- **shared-models/**: Database models, Pydantic schemas, and Alembic migrations
- **shared-clients/**: HTTP client libraries for external API access (user-facing endpoints)
- **helm/**: Kubernetes Helm charts for OpenShift deployment
- **test/**: Testing utilities and scripts

## Development Commands

### Build System (Makefile)

All development operations use the root Makefile:

```bash
# Install dependencies for all services
make deps-all

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
make test-request-manager
```

### Container Operations

The project uses templated Containerfiles for consistency:

```bash
# Build using templates with build args
make build-request-mgr-image    # Uses Containerfile.services-template
make build-mcp-snow-image       # Uses Containerfile.mcp-template

# Push to registry
make push-all-images
```

### Helm Deployment

The system supports three deployment modes:

```bash
# 1. Testing/Development Mode (Mock Eventing - Default)
make helm-install-test NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SLACK_SIGNING_SECRET="your-secret" \
  SNOW_API_KEY="your-key"

# 2. Production Mode (Full Knative Eventing)
make helm-install-prod NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SLACK_SIGNING_SECRET="your-secret" \
  SNOW_API_KEY="your-key"

# Check deployment status
make helm-status NAMESPACE=your-namespace

# Uninstall with cleanup (removes Helm release, test-email-server, jobs, PVCs, etc.)
make helm-uninstall NAMESPACE=your-namespace
# Or: make uninstall NAMESPACE=your-namespace (removes deployment + namespace)

# Shorthand: make install = helm-install-test by default; override with INSTALL_MODE=demo|prod
make install NAMESPACE=your-namespace                    # same as helm-install-test
make install NAMESPACE=your-namespace INSTALL_MODE=demo  # same as helm-install-demo

# 3. Demo Mode
# Option A: Helm-only (Greenmail + demo values)
make helm-install-demo NAMESPACE=your-namespace
# Option B: Helm export + Ansible (ephemeral, conference demos)
make ansible-apply-demo NAMESPACE=your-namespace
# See docs/HELM_EXPORT_ANSIBLE.md for env vars and export-then-apply workflow

# Optional: Zammad + ticketing profile (deploy Zammad, MCP wiring; see README)
# make helm-install-ticketing NAMESPACE=your-namespace
```

#### Zammad MCP naming (do not rename lightly)

The MCP server entry under **`mcp-servers.mcp-servers`** must use the key **`zammad-mcp`**, not **`zammad`**. The Zammad Helm subchart already labels its pods with `app.kubernetes.io/name: zammad`. The upstream `mcp-servers` chart derives labels from the YAML key; using `zammad` made Service **`mcp-zammad`** select **all** Zammad workload pods (nginx, railsserver, etc.), so traffic to `:8000` often hit pods that are not the MCP server (`connection refused`). With **`zammad-mcp`**, the MCP Service is **`mcp-zammad-mcp`** and only targets the MCP deployment. Agent MCP URIs use **`http://mcp-zammad-mcp:8000/mcp`**. See the comment above `zammad-mcp` in `helm/values.yaml` and `mcp-servers/zammad/README.md`.

In **agent** YAML (`config/agents/*.yaml`, `mcp_servers[].name`), use the label **`zammad`** for the MCP server (tracing / `server_label`); that is unrelated to the Helm values key **`zammad-mcp`**.

**Zammad webhooks:** `POST /zammad/webhook` on integration-dispatcher **always** verifies **`X-Hub-Signature`** against **`ZAMMAD_WEBHOOK_SECRET`** (set via `ticketingZammad.webhookSecret` / Helm secrets). An empty secret yields **401** — there is no “skip verification” mode. Customer-visible replies are posted by **`ZammadIntegrationHandler`** to Zammad REST using a pooled HTTP client from **shared-clients**; optional **`ZAMMAD_AI_AGENT_USER_ID`** drops webhook feedback from the API user that posts those articles. Use **`shared_models.utils`** (`normalize_zammad_rest_api_base`, **`zammad_rest_json_headers`**, **`zammad_rest_authorization_headers`**) for any other Zammad REST calls so URL and auth headers stay consistent.

## Architecture

### Core Components

1. **Agent Service**: Processes AI requests via LlamaStack, handles streaming responses, manages knowledge bases and session management
2. **Request Manager**: Routes requests, unified communication processing with strategy pattern
3. **Integration Dispatcher**: Delivers responses to multiple channels (Slack, Email, etc.)
4. **MCP Servers**: External tool integration (ServiceNow MCP, Zammad MCP for ticketing actions)
5. **Mock Eventing Service**: Lightweight service that mimics Knative broker behavior for testing
6. **Shared Database**: PostgreSQL with Alembic migrations for session/request persistence

### Communication Architecture

The system supports two communication modes (both eventing-based):

#### **1. Testing/Development Mode (Mock Eventing - Default)**
- **Mock Eventing Service**: Lightweight service that mimics Knative broker behavior
- **Request Flow**: API → Request Manager → Agent Service → Integration Dispatcher
- **No Knative Infrastructure**: Perfect for testing, development, and CI/CD without full Knative setup
- **Identical Behavior**: Same event-driven patterns as production with mock infrastructure
- **Low Resource Usage**: Minimal dependencies for simple deployments

#### **2. Production Mode (Full Knative Eventing)**
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
- **Templated Containerfiles**: `Containerfile.services-template` and `Containerfile.mcp-template` for consistency
- **Red Hat UBI**: Uses `registry.access.redhat.com/ubi9/python-312-minimal` base images
- **Multi-stage builds**: Optimized Docker layer caching
- **OpenShift**: Helm charts designed for OpenShift with Routes, NetworkPolicies

### Key Environment Variables

- `LLAMA_STACK_URL`: LlamaStack service endpoint (default: http://llamastack:8321)
- `BROKER_URL`: Knative broker endpoint for CloudEvents (or mock eventing service URL) - required for eventing
- `DATABASE_URL`: PostgreSQL connection string
- `SLACK_SIGNING_SECRET`: Slack webhook verification
- `SNOW_API_KEY`, `HR_API_KEY`: External service API keys
- `SAFETY`: Safety model for content moderation (e.g., meta-llama/Llama-Guard-3-8B)
- `SAFETY_URL`: LlamaStack API endpoint for moderation (if shields enabled)
- `LLM_MAX_TOKENS`: Max output tokens for the LLM when deploying with Makefile and `LLM=` (default 2048). Set in Helm as `global.models.<LLM>.maxTokens`; see `helm/values.yaml` and [Prompt Configuration Guide](guides/PROMPT_CONFIGURATION_GUIDE.md).

## Code Standards

- Format all Python code with `black`
- Lint with `flake8` 
- Use type hints and docstrings
- Follow PEP 8 guidelines
- Python 3.12+ required

## Local Development

### Development Workflow

```bash
# 1. Install all dependencies
make deps-all

# 2. Run linting and formatting
make lint
make format

# 3. Build and test locally
make build-all-images
make test-all

# 4. Deploy to OpenShift (testing/development mode with mock eventing)
make helm-install-test NAMESPACE=dev
```

## Documentation

### Core Documentation
- **`docs/HELM_EXPORT_ANSIBLE.md`**: Demo deployment (helm export + Ansible), env vars, export-then-apply
- **`docs/API_REFERENCE.md`**: Complete API documentation and endpoints
- **`docs/SESSION_SERIALIZATION_RUNBOOK.md`**: Session request serialization (one-per-session FIFO, reclaim) — env vars, stuck/failed behavior, test strategy
- **`guides/INTEGRATION_GUIDE.md`**: Complete integration and request management guide
- **`guides/SAFETY_SHIELDS_GUIDE.md`**: Safety shields and content moderation configuration
- **`guides/PERFORMANCE_SCALING_GUIDE.md`**: Performance characteristics, scaling strategies, and optimization approaches
- **`docs/ARCHITECTURE_DIAGRAMS.md`**: System architecture and flow diagrams
- **`docs/CHANNEL_BEHAVIOR.md`**: Per-integration session policy, delivery binding, registry, adding channels
- **`guides/AUTHENTICATION_GUIDE.md`**: Enhanced security and authentication setup with production readiness warnings
- **`guides/SLACK_SETUP.md`**: Slack app configuration guide

### Component Documentation
- **`agent-service/`**: Agent service with knowledge base management and LangGraph
- **`mcp-servers/snow/README.md`**: ServiceNow integration documentation
- **`mcp-servers/zammad/README.md`**: Zammad MCP (ticket tools; customer replies go through Integration Dispatcher)

### Unified Architecture
The system uses eventing-based communication with the following core components:
- **`CommunicationStrategy`**: Abstract base class for communication mechanisms
- **`EventingStrategy`**: Handles CloudEvent-based communication (default and only strategy)
- **`UnifiedRequestProcessor`**: Central request processing logic for eventing
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

### Safety & Content Moderation
- **Input Shields**: Validate user input before processing using Llama Guard 3 or compatible models
- **Output Shields**: Check agent responses before delivery to users
- **Category Filtering**: Configure ignored categories to handle false positives in business workflows
- **Llama Guard Integration**: OpenAI-compatible moderation API via LlamaStack
- **Per-Agent Configuration**: Enable shields selectively based on agent risk profile

## Related Documentation

- [README.md](../README.md) - Main project documentation
- [GUIDELINES.md](GUIDELINES.md) - Code practices and project structure guidelines
