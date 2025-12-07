# PromptGuard Service

A lightweight service for detecting prompt injection attacks and jailbreak attempts in AI agent interactions. PromptGuard uses Llama Prompt Guard 2 model to classify user input as "safe" or "unsafe" before processing.

## Overview

PromptGuard is the first layer of defense in a defense-in-depth security strategy for AI agents. It specifically targets:
- **Prompt injection attacks**: Attempts to manipulate the AI system through crafted inputs
- **Jailbreak attempts**: Techniques to bypass safety restrictions
- **Malicious user input**: Content designed to exploit the AI system

## How It Works

The service provides an OpenAI-compatible API endpoint (`/v1/chat/completions`) that:
1. Extracts the user message from the conversation
2. Runs inference using the Llama Prompt Guard 2 model
3. Returns a classification: `"safe"` or `"unsafe"`
4. Provides confidence scores for monitoring

The service is designed to be lightweight (86M model) and can run on CPU, making it suitable for production deployments.

## Deployment

### Build and Push Image

```bash
# Build the PromptGuard service image
make build-promptguard-image

# Push to registry
make push-promptguard-image
```

### Environment Variables

PromptGuard requires the following environment variables:

```bash
export PROMPTGUARD_ENABLED=true  # Required Makefile variable to enable PromptGuard
export HF_TOKEN=your-huggingface-token  # Required for gated models
```

**Optional environment variables:**
- `PROMPTGUARD_MODEL_ID`: Model identifier (defaults to `meta-llama/Llama-Prompt-Guard-2-86M`)

### Configuration Options

Configure PromptGuard in `helm/values.yaml`:

```yaml
promptGuard:
  enabled: true
  replicas: 1
  modelId: "meta-llama/Llama-Prompt-Guard-2-86M"
  huggingfaceToken: ""  # Required for gated models
  resources:
    limits:
      cpu: "2"
      memory: 2Gi
    requests:
      cpu: "1"
      memory: 1Gi
```

## Integration with Agent Service

PromptGuard is automatically integrated when configured in agent YAML files:

```yaml
# agent-service/config/agents/your-agent.yaml
input_shields:
  - "meta-llama/Llama-Prompt-Guard-2-86M"  # First layer: attack detection
  - "meta-llama/Llama-Guard-3-8B"          # Second layer: content safety
```

The agent service will route shield requests to the PromptGuard service at:
`http://self-service-agent-promptguard.<namespace>.svc.cluster.local:8000/v1`

## API Endpoints

- `GET /health`: Health check endpoint
- `GET /v1/models`: List available models (OpenAI-compatible)
- `POST /v1/chat/completions`: Classify user input as safe/unsafe
