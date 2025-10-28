# Safety Shields Guide

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Configuration](#configuration)
4. [Shield Models](#shield-models)
5. [Ignored Categories](#ignored-categories)
6. [Related Documentation](#related-documentation)

---

## Overview

Safety shields provide content moderation and safety checking for AI agent interactions. The system supports both **input shields** (validating user messages before processing) and **output shields** (checking agent responses before delivery to users).

### Key Benefits

- **User Safety**: Prevent harmful or inappropriate content from reaching users
- **Content Moderation**: Validate user input against safety policies
- **Compliance**: Meet organizational content safety requirements
- **False Positive Handling**: Configure category-specific filtering to reduce false positives in business contexts

### When to Use Safety Shields

- **High-Risk Applications**: Customer-facing agents handling sensitive topics
- **Compliance Requirements**: Organizations with strict content policies
- **Public-Facing Systems**: Agents accessible to external users
- **Multi-Tenant Environments**: Systems serving multiple organizations

---

## How It Works

### Architecture

The safety shield system operates at the agent service level, checking content before and after LLM processing:

```
User Input → Input Shield → LLM Processing → Output Shield → User Response
              ↓ (if unsafe)                    ↓ (if unsafe)
         Blocked Response                 Blocked Response
```

### Input Shields

Input shields validate user messages **before** they are processed by the LLM:

1. **User sends message** to the agent
2. **Input shield checks** the last user message against configured models
3. **If unsafe**: Return error message to user, do not process
4. **If safe**: Continue to LLM processing

**Note**: Input shields only check the **last message** in the conversation (the most recent user input), not the entire conversation history. This improves performance and focuses on the current user input.

### Output Shields

Output shields validate agent responses **before** they are delivered to users:

1. **Agent generates response** from LLM
2. **Output shield checks** the complete response
3. **If unsafe**: Return generic error message instead of generated response
4. **If safe**: Deliver response to user

### Integration with LlamaStack

Safety shields use the **OpenAI-compatible moderation API** provided by LlamaStack:

- Shields call the `/v1/moderations` endpoint
- Support for Llama Guard and other compatible models
- Returns category-based flagging results
- Compatible with standard OpenAI moderation response format

---

## Configuration

### Environment Variables

Safety shields require two environment variables to be configured:

```bash
# The safety model to use (e.g., Llama Guard 3)
SAFETY=meta-llama/Llama-Guard-3-8B

# OpenAI-compatible moderation API endpoint
SAFETY_URL=https://api.example.com/v1
```

**Important**:
- Replace `https://api.example.com/v1` with your actual moderation API endpoint
- For in-cluster deployments, you can use a vLLM instance (e.g., `http://vllm-service:8000/v1`)
- If these environment variables are not set, shields will be **automatically disabled** even if configured in agent YAML files. A warning will be logged.

### Agent Configuration

Configure shields in your agent YAML file (e.g., `agent-service/config/agents/laptop-refresh-agent.yaml`):

```yaml
name: "laptop-refresh"
description: "An agent that can help with laptop refresh requests."
system_message: "You are a helpful laptop refresh assistant."

# Input shields - validate user input before processing
input_shields: ["meta-llama/Llama-Guard-3-8B"]

# Output shields - validate agent responses before delivery
output_shields: []

# Categories to ignore for false positives
ignored_input_shield_categories:
  - "Code Interpreter Abuse"  # Normal tool/MCP usage flagged incorrectly
  - "Specialized Advice"      # IT support requests flagged as specialized advice
  - "Privacy"                 # Employee info requests are legitimate in IT support context
  - "Self-Harm"              # False positives on common words like "yes"

ignored_output_shield_categories: []
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `input_shields` | list[str] | List of shield model names for input validation |
| `output_shields` | list[str] | List of shield model names for output validation |
| `ignored_input_shield_categories` | list[str] | Categories to ignore in input checking (false positive handling) |
| `ignored_output_shield_categories` | list[str] | Categories to ignore in output checking (false positive handling) |

### Helm Chart Configuration

Set the safety environment variables in your Helm deployment:

```bash
make helm-install-test \
  NAMESPACE=your-namespace \
  LLM=llama-3-2-1b-instruct \
  SAFETY=meta-llama/Llama-Guard-3-8B \
  SAFETY_URL=https://api.example.com/v1
```

**Note**: Replace `https://api.example.com/v1` with your actual moderation API endpoint. For in-cluster deployments, you can use a vLLM instance (e.g., `http://vllm-service:8000/v1`).

Alternatively, configure in your `values.yaml`:

```yaml
requestManagement:
  agentService:
    env:
      SAFETY: "meta-llama/Llama-Guard-3-8B"
      SAFETY_URL: "https://api.example.com/v1"
```

---

## Shield Models

### Llama Guard 3

**Model Name**: `meta-llama/Llama-Guard-3-8B`

Llama Guard 3 is Meta's content safety classifier designed to detect harmful content across multiple categories.

**Supported Categories**:
- Violent Crimes
- Non-Violent Crimes
- Sex-Related Crimes
- Child Sexual Exploitation
- Defamation
- Specialized Advice (Financial, Medical, Legal)
- Privacy Violations
- Intellectual Property
- Indiscriminate Weapons
- Hate Speech
- Suicide & Self-Harm
- Sexual Content
- Elections
- Code Interpreter Abuse

**Use Cases**:
- General-purpose content moderation
- Customer-facing applications
- Multi-category safety checking

### Other Compatible Models

Any model compatible with the OpenAI moderation API format can be used:

```yaml
input_shields:
  - "meta-llama/Llama-Guard-3-8B"
  - "your-custom-model"
```

---

## Ignored Categories

### Why Ignore Categories?

Safety models can produce **false positives** in business contexts where certain content is legitimate. For example:

- **IT Support Context**: Questions about employee information are normal
- **Tool Usage**: Using MCP tools/APIs may be flagged as "Code Interpreter Abuse"
- **Business Advice**: IT recommendations may be flagged as "Specialized Advice"

### Configuring Ignored Categories

Add categories to ignore in your agent configuration:

```yaml
ignored_input_shield_categories:
  - "Code Interpreter Abuse"  # Allow normal tool usage
  - "Specialized Advice"      # Allow IT support recommendations
  - "Privacy"                 # Allow employee info requests
  - "Self-Harm"              # Avoid false positives on common words
```

### How It Works

When a shield flags content:

1. **Check flagged categories** against ignored list
2. **If all flagged categories are ignored**: Allow content (treat as safe)
3. **If any flagged category is NOT ignored**: Block content

**Example**:
```
Flagged categories: ["Privacy", "Specialized Advice"]
Ignored categories: ["Privacy", "Specialized Advice"]
Result: ALLOWED (all flagged categories are in ignored list)

Flagged categories: ["Privacy", "Violent Crimes"]
Ignored categories: ["Privacy"]
Result: BLOCKED (Violent Crimes is not ignored)
```

## Related Documentation

- [Agent Configuration Guide](../docs/PROMPT_CONFIGURATION_GUIDE.md) - LangGraph and agent setup
- [API Reference](../docs/API_REFERENCE.md) - Complete API documentation
- [Architecture Diagrams](../docs/ARCHITECTURE_DIAGRAMS.md) - System architecture
