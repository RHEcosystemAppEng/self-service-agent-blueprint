# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a self-service agent blueprint implementing an AI agent management system with LlamaStack integration. The project consists of:

- **agent-manager/**: Core Python module for managing AI agents with LlamaStack
- **deploy/helm/**: Kubernetes Helm charts for OpenShift deployment
- **test/**: Testing utilities and scripts

## Development Commands

### Agent Manager Module (Python)

Navigate to `agent-manager/` directory for all Python development:

```bash
# Sync project dependencies
uv sync --all-packages

# Run unit tests
uv run pytest

# Code formatting and linting
uv run black .
uv run flake8 .

# Run the agent registration script
uv run script/register_agents.py
```

### Container Operations

```bash
# Build agent-manager container
cd agent-manager/
podman build -t agent-manager .

# Run with LlamaStack connection
podman run --rm -e LLAMASTACK_SERVICE_HOST="http://{{LLAMA_STACK_IP}}:8321" --network bridge agent-manager
```

### Helm Deployment

```bash
cd deploy/helm/
make install NAMESPACE=your-namespace

# Check deployment status
make status NAMESPACE=your-namespace

# Uninstall
make uninstall NAMESPACE=your-namespace
```

## Architecture

### Core Components

1. **AgentManager**: Central class in `agent-manager/src/agent_manager/agent_manager.py` that manages LlamaStack client connections and agent lifecycle
2. **Configuration**: YAML-based configuration in `agent-manager/config/` for agents and service settings
3. **LlamaStack Integration**: Uses `llama-stack-client` for AI model interactions

### Project Structure

- Uses UV for Python package management and virtual environments
- Follows modern Python packaging with `src/` layout
- Containerized deployment with Podman/Docker
- Kubernetes deployment via Helm charts for OpenShift

### Key Environment Variables

- `LLAMASTACK_SERVICE_HOST`: Required for agent-manager to connect to LlamaStack service
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DBNAME`: Database configuration for Helm deployment
- `HF_TOKEN`: Hugging Face token for model access

## Code Standards

- Format all Python code with `black`
- Lint with `flake8` 
- Use type hints and docstrings
- Follow PEP 8 guidelines
- Python 3.12+ required

## Local Development

For local testing with LlamaStack:
1. Run Ollama server: `OLLAMA_HOST=0.0.0.0 ollama serve`
2. Start LlamaStack container (see `agent-manager/local_testing/README.md`)
3. Set `LLAMASTACK_SERVICE_HOST=http://localhost:8321`
4. Run agent registration script