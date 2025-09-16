# Self-Service Agent Blueprint

A comprehensive blueprint for building self-service AI agents with modular components including asset management, employee information services, and Helm-based deployment.

## Project Structure

- **`asset-manager/`** - Asset management module for agents and knowledge bases
- **`mcp-servers/employee-info/`** - Employee information MCP server
- **`helm/`** - Helm charts for Kubernetes deployment
- **`test/`** - Root project tests

## Quick Start

### Prerequisites

- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [Podman](https://podman.io/) or Docker - Container runtime
- [Helm](https://helm.sh/) - Kubernetes package manager (for deployment)
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) - Kubernetes Command line tool

### Installation

Install all project dependencies:

```bash
make install-all
```

Or install specific components:

```bash
make install                    # Self-service agent dependencies
make install-asset-manager      # Asset manager dependencies
make install-mcp-emp-info       # Employee info MCP dependencies
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
make test-mcp-emp-info          # Run tests for employee info MCP
```

### Container Operations

#### Building Images

```bash
make build-all-images           # Build all container images
make build-agent-image          # Build self-service agent image
make build-asset-mgr-image      # Build asset manager image
make build-mcp-emp-info-image   # Build employee info MCP image
```

#### Pushing Images

```bash
make push-all-images            # Push all images to registry
make push-agent-image           # Push self-service agent image
make push-asset-mgr-image       # Push asset manager image
make push-mcp-emp-info-image    # Push employee info MCP image
```

### Deployment

#### Helm Operations

```bash
make helm-depend                # Update Helm dependencies
make helm-list-models           # List available models
```

#### Deploy to Kubernetes/OpenShift

```bash
# Set your namespace
export NAMESPACE=your-namespace

# Install the complete stack
make helm-install

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

Run `make help` to see all available commands with descriptions.

## Component Documentation

- [Asset Manager](asset-manager/README.md) - Detailed asset manager documentation
- [Employee Info MCP](mcp-servers/employee-info/README.md) - Employee information service documentation

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

### Try