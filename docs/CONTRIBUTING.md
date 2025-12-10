# Contributing to Self-Service Agent Blueprint

Thank you for your interest in contributing to the Self-Service Agent Blueprint! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
  - [Local Setup](#local-setup)
  - [Local Development with Kind Cluster](#local-development-with-kind-cluster)
- [Development Commands](#development-commands)
  - [Quick Reference](#quick-reference)
  - [Code Quality](#code-quality)
  - [Testing](#testing)
  - [Container Operations](#container-operations)
  - [Helm Operations](#helm-operations)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Documentation](#documentation)
- [Questions](#questions)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and collaborative environment for all contributors.

## How Can I Contribute?

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OpenShift version, LLM model, deployment mode)
- Relevant logs or error messages

### Suggesting Enhancements

We welcome suggestions for:
- New features or use cases
- Improvements to existing functionality
- Documentation improvements
- Evaluation metrics
- MCP server integrations

### Contributing Code

We appreciate contributions including:
- Bug fixes
- New features
- Documentation updates
- Test improvements
- New agent configurations
- MCP server implementations
- Knowledge base content
- Evaluation metrics

## Development Setup

### Prerequisites

Ensure you have the required tools installed:
- Python 3.12+
- uv (Python package manager)
- Podman
- OpenShift CLI (oc)
- kubectl
- Helm
- Git
- Make

### Local Setup

1. **Clone the repository:**

   Get the repository URL by clicking the green **Code** button at the top of the repository page, then:

   ```bash
   git clone <repository-url>
   cd <repository-directory>  # The directory name matches the repository name
   ```

2. **Install dependencies:**
   ```bash
   make install-all
   ```

   Or install specific components:
   ```bash
   make install                    # Self-service agent dependencies
   make install-request-manager    # Request manager dependencies
   make install-agent-service      # Agent service dependencies
   make install-integration-dispatcher  # Integration dispatcher dependencies
   make install-mcp-snow          # ServiceNow MCP dependencies
   ```

3. **Run tests:**
   ```bash
   make test-all
   ```

### Local Development with Kind Cluster

For local Kubernetes development without OpenShift, you can run a local Kind cluster with a container registry:

1. **Create Kind cluster with registry:**
   ```bash
   sh ./scripts/ci/kind-with-registry.sh
   ```

2. **Build and push images to local registry:**
   ```bash
   export REGISTRY=localhost:5001
   make build-all-images
   make push-all-images
   ```

3. **Deploy to Kind cluster:**
   ```bash
   export NAMESPACE=dev
   make helm-install-test NAMESPACE=$NAMESPACE
   ```

4. **Clean up when done:**
   ```bash
   kind delete cluster
   ```

   **Note:** Images will be cached on the registry container and survive cluster deletion.

## Development Commands

### Quick Reference

To see all available make commands with descriptions:
```bash
make help
```

This displays all available targets including deployment modes, testing commands, and build options.

### Code Quality

**Formatting:**
```bash
make format                     # Run Black formatting on entire codebase
```

**Linting:**
```bash
make lint                       # Run flake8 linting on entire codebase
```

Always run these before committing your changes.

### Testing

**Run all tests:**
```bash
make test-all                   # Run tests for all projects
```

**Run component-specific tests:**
```bash
make test                       # Run tests for self-service agent
make test-request-manager       # Run tests for request manager
make test-agent-service         # Run tests for agent service
make test-integration-dispatcher # Run tests for integration dispatcher
make test-mcp-snow             # Run tests for ServiceNow MCP
```

### Container Operations

> **Note**: Container images do not include HEALTHCHECK instructions as health monitoring is handled by Kubernetes liveness and readiness probes in the Helm deployment.

**Default Registry:**

By default, container images are built for `quay.io/ecosystem-appeng`. You can override this by setting the `REGISTRY` environment variable (see examples below).

#### Building Container Images

**Build all images:**
```bash
make build-all-images           # Build all container images
```

**Build individual images:**
```bash
make build-request-mgr-image    # Build request manager image
make build-agent-service-image  # Build agent service image
make build-integration-dispatcher-image  # Build integration dispatcher image
make build-mcp-snow-image       # Build ServiceNow MCP image
```

**Build for ARM architecture:**
```bash
make build-all-images REGISTRY=quay.io/<user> ARCH="linux/arm64"
```

**Use custom registry:**
```bash
export REGISTRY=your-registry.com/your-org
make build-all-images
```

**Build with specific version:**
```bash
export VERSION=1.0.0
make build-all-images
```

#### Pushing Container Images

**Push all images:**
```bash
make push-all-images            # Push all images to registry
```

**Push individual images:**
```bash
make push-request-mgr-image     # Push request manager image
make push-agent-service-image   # Push agent service image
make push-integration-dispatcher-image  # Push integration dispatcher image
make push-mcp-snow-image        # Push ServiceNow MCP image
```

### Helm Operations

```bash
make helm-depend                # Update Helm dependencies
make helm-list-models           # List available models
make helm-status                # Check deployment status
```

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following our [coding standards](#coding-standards)

3. **Test your changes:**
   ```bash
   make lint
   make format
   make test-all
   ```

4. **Build container images:**
   ```bash
   export REGISTRY=quay.io/youruser
   make build-all-images
   ```

5. **Push images to registry:**
   ```bash
   make push-all-images
   ```

6. **Deploy to OpenShift test environment:**

   Set required environment variables:
   ```bash
   export NAMESPACE=dev-test
   export LLM=llama-3-3-70b-instruct-w8a8
   export LLM_ID=llama-3-3-70b-instruct-w8a8
   export LLM_API_TOKEN=your-api-token
   export LLM_URL=https://your-llm-endpoint
   export HF_TOKEN=1234
   ```

   Deploy with Helm:
   ```bash
   make helm-install-test NAMESPACE=$NAMESPACE
   ```

   Wait for all pods to be running:
   ```bash
   oc get pods -n $NAMESPACE
   ```

7. **Run evaluations to ensure quality:**
   ```bash
   make test-short-resp-integration-request-mgr
   ```

   **Important:** All evaluations must pass before submitting your PR. This validates that your changes maintain agent quality and don't introduce regressions.

8. **Clean up test deployment:**
   ```bash
   make helm-uninstall NAMESPACE=$NAMESPACE
   ```

9. **Commit your changes** with clear, descriptive messages:
   ```bash
   git add .
   git commit -m "feat: add new MCP server for HR system"
   ```

   Use conventional commit messages:
   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation changes
   - `test:` - Test additions or fixes
   - `chore:` - Maintenance tasks

10. **Push to your fork:**
    ```bash
    git push origin feature/your-feature-name
    ```

11. **Create a Pull Request** with:
   - Clear title and description
   - Reference to related issues
   - Description of changes made
   - Testing performed
   - Screenshots (if UI changes)

### Review Process

- All submissions require review before merging
- Reviewers may request changes or improvements
- Address feedback and update your PR
- Once approved, maintainers will merge your contribution

## Coding Standards

### Python Code

- **Format code** with Black:
  ```bash
  make format
  ```

- **Use type hints:**
  ```python
  def process_request(request: Request) -> Response:
      pass
  ```

- **Add docstrings** for functions and classes:
  ```python
  def create_agent(config: AgentConfig) -> Agent:
      """Create and register a new agent with LlamaStack.

      Args:
          config: Agent configuration including instructions and tools

      Returns:
          Registered agent instance
      """
      pass
  ```

- **Follow PEP 8** style guidelines
- **Run linting** before committing:
  ```bash
  make lint
  ```

### Configuration Files

- **Agent configs**: Use YAML format in `agent-service/config/agents/`
- **Knowledge bases**: Place text files in `agent-service/config/knowledge_bases/`
- **Helm values**: Follow existing structure in `helm/values.yaml`

### Documentation

- Update relevant documentation when making changes
- Include code examples where helpful
- Update API documentation if endpoints change
- Add evaluation examples for new use cases

## Documentation

### What to Document

- **New features**: Update relevant README files
- **API changes**: Update [`API_REFERENCE.md`](API_REFERENCE.md)
- **Architecture changes**: Update [`ARCHITECTURE_DIAGRAMS.md`](ARCHITECTURE_DIAGRAMS.md)
- **New integrations**: Create guide in `docs/` or component README
- **Configuration changes**: Update quickstart and setup guides

### Documentation Style

- Use clear, concise language
- Include code examples
- Add "Expected outcome" sections for procedures
- Use proper markdown formatting
- Link to related documentation

## Questions?

If you have questions about contributing:

- Review the [Quickstart Guide](../README.md) for system overview and architecture
- Check existing documentation in `docs/`
- Review component-specific README files
- Check existing issues for similar questions
- Open a new issue with the `question` label

### Helpful Documentation

- [README.md](../README.md) - Quickstart guide and system overview
- [CLAUDE.md](CLAUDE.md) - Development guidance for Claude Code
- [GUIDELINES.md](GUIDELINES.md) - Code practices and project structure guidelines
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation
- [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) - System architecture diagrams
- [INTEGRATION_GUIDE.md](../guides/INTEGRATION_GUIDE.md) - Integration patterns and guides
- [AUTHENTICATION_GUIDE.md](../guides/AUTHENTICATION_GUIDE.md) - Authentication setup
- Component READMEs in each service directory

---

## License

By contributing to this project, you agree that your contributions will be licensed under the Apache License 2.0.

---

**Thank you for contributing to the Self-Service Agent Blueprint!**
