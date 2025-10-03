# Prompt Configuration Guide

This guide explains how to create and configure YAML-based prompt configuration files for LangGraph agents in the self-service agent blueprint.

## LangGraph Overview

Under the covers, [LangGraph](https://github.com/langchain-ai/langgraph) is used to create and manage state machines that implement the desired conversation flow for each agent. The YAML configuration approach allows you to define complex agent behaviors without writing code, making it easy to modify and maintain agent implementations.

## Configuration Styles

This blueprint supports two main configuration styles, each optimized for different use cases:

### 1. Simple Graph with Large Prompt

A minimal state machine with one comprehensive prompt that guides the entire workflow.

**Advantages:**
- Easier to write and understand
- More flexible for handling unexpected user inputs
- LLM manages the workflow autonomously
- Fewer state transitions to debug

**Disadvantages:**
- Requires larger, more capable models (e.g., 70B+ parameters)
- Less control over conversation flow
- Harder to enforce specific validation steps
- Higher token usage per interaction

**Best for:** Complex, conversational workflows where the LLM can self-manage the process.

**Example:** `lg-prompt-big.yaml`

### 2. Detailed Graph with State-Specific Prompts

An explicit state machine with dedicated states for each process step and focused prompts.

**Advantages:**
- May works with smaller models
- Precise control over workflow progression
- Easier to enforce validation and error handling
- Lower token usage per LLM call

**Disadvantages:**
- More complex configuration to write and maintain
- Less flexible for unexpected user inputs
- Requires planning all possible conversation paths
- More states to debug and test

**Best for:** Structured workflows with clear steps, validation requirements, or smaller models.

**Example:** `lg-prompt-small.yaml`

## Overview

Prompt configuration files define state machine behavior for agents, including:
- State definitions and transitions
- LLM prompts and temperature settings
- Data storage and business logic fields
- Tool usage and permissions
- Intent classification and response analysis

## File Location

Prompt configuration files are stored in:
```
asset-manager/config/lg-prompts/
```

## Basic Structure

Every prompt configuration file follows this structure:

```yaml
# Global settings
settings:
  initial_state: "state_name"
  terminator_env_var: "AGENT_MESSAGE_TERMINATOR"
  agent_name: "agent-name"
  terminal_state: "end"
  empty_response_retry_count: 3

# State structure definition
state_schema:
  business_fields:
    field_name:
      type: "string|dict|boolean"
      description: "Field purpose"
      default: null

# State definitions
states:
  state_name:
    type: "llm_processor|waiting|intent_classifier|terminal"
    # ... state configuration
```

## Settings Section

### Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| `initial_state` | First state when agent starts | `"greet_and_identify_need"` |
| `agent_name` | Unique identifier for the agent | `"laptop-refresh"` |
| `terminal_state` | Final state name | `"end"` |
| `terminator_env_var` | Environment variable name for termination signal. Used by the evaluations framework to identify the end of an agent message. | `"AGENT_MESSAGE_TERMINATOR"` |

### Optional Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `empty_response_retry_count` | Number of retries for empty LLM responses. Agents occasionally return empty responses, retrying can improve success rates. | `3` |
| `initial_user_message` | Auto-inject first user message to help the agent start correctly. When present, this replaces any message passed from agent handover. | None |

## State Schema

Define workflow-specific fields that store data throughout the conversation. Fields are set by one state and can be referenced in prompts and transitions of subsequent states. As an example: 

```yaml
state_schema:
  business_fields:
    employee_info:
      type: "dict"
      description: "Employee information from lookup"
      default: null

    eligibility_status:
      type: "string"
      description: "ELIGIBLE, NOT_ELIGIBLE, or UNCLEAR"
      default: null

    ticket_created:
      type: "boolean"
      description: "Whether ServiceNow ticket was created"
      default: false
```

### Field Types

- **`string`**: Text data
- **`dict`**: Structured object/JSON data
- **`list`**: Array of dictionaries
- **`boolean`**: True/false values
- **`null`**: Empty by default (can be used with any type)

## State Types

The framework supports five state types:

1. **`llm_processor`**: Executes LLM calls with prompts and tools
2. **`waiting`**: Pauses for user input
3. **`intent_classifier`**: Classifies user intent and routes accordingly
4. **`terminal`**: Marks conversation end with optional reset
5. **`llm_validator`**: Validates user input using LLM with conversation context

### 1. LLM Processor State

Executes an LLM call with a prompt:

```yaml
state_name:
  type: "llm_processor"
  temperature: 0.3
  allowed_tools: ["tool_name"]  # Optional: restrict tool access
  prompt: |
    Your prompt here.
    Can reference fields: {employee_info.response}
    Can reference user input: {last_user_message}

  transitions:
    success: "next_state"

  data_storage:
    field_name: "llm_response"
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | State type identifier | `"llm_processor"` |
| `prompt` | LLM instruction template with variable interpolation | `"You are a helpful assistant..."` |
| `transitions` | Maps completion conditions to next states | `success: "next_state"` |

**Note:** Use either `prompt` or `conditional_prompts` (see below), but not both.

#### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `temperature` | Controls response randomness (0.0-1.0). | `0.7` |
| `allowed_tools` | Array of tool names the LLM can access. Use `["tool_name"]` for specific tools, `[""]` to disable all tools, or omit for unrestricted access. | Unrestricted |
| `uses_tools` | String flag to disable tool usage. Set to `"No"` to prevent all tool calls. | Tools enabled |
| `uses_mcp_tools` | String flag to disable MCP tool usage. Set to `"No"` to prevent MCP tool calls while allowing other tools. | MCP tools enabled |
| `use_conversation_history` | Use agent and user messages as context with the prompt as system message. By default no message history is maintained and configured prompt (which may include information from previous states that was stored in the state) is the only context provided to the request. | `false` |
| `conditional_prompts` | Array of conditional prompt configurations (see below). Alternative to `prompt` for field-based prompt selection. | None |
| `data_storage` | Map field names to `"llm_response"` to store LLM output in state schema fields. | None |
| `response_analysis` | Define trigger phrases and actions based on LLM response content (see Response Analysis section). | None |

#### Conditional Prompts

Execute different prompts based on field values:

```yaml
select_laptop:
  type: "llm_processor"
  conditional_prompts:
    - condition: "user_is_ineligible"
      check_field: "eligibility_status"
      check_phrases: ["NOT_ELIGIBLE"]
      prompt: |
        Show laptops with ineligibility warning.

    - condition: "field_is_empty"
      check_field: "selected_laptop"
      check_empty: true
      prompt: |
        No laptop selected yet.

    - condition: "default"
      prompt: |
        Show standard laptop options.
```

**Conditional Prompt Parameters:**

| Parameter | Description | Required |
|-----------|-------------|----------|
| `condition` | Name for this condition (use `"default"` for fallback) | Yes |
| `prompt` | Prompt text to use when condition matches | Yes |
| `check_field` | Field name to evaluate | No |
| `check_phrases` | Array of phrases to match in field value | No |
| `check_empty` | Boolean: `true` to check if field is empty, `false` to check if not empty | No |

**Important Notes:**

1. Use either `check_phrases` or `check_empty`, not both
2. Conditions are evaluated in order; first match wins
3. **Tool configuration is state-level only**: `allowed_tools`, `uses_tools`, and `uses_mcp_tools` are set at the state level and apply to **all** conditional prompts within that state.

### 2. Waiting State

Pauses for user input.

```yaml
waiting_user_need:
  type: "waiting"
  transitions:
    user_input: "classify_user_intent"
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | State type identifier | `"waiting"` |
| `transitions` | Maps user input event to next state | `user_input: "next_state"` |

**Note:** Always pair waiting states with a classification or processing state.

### 3. Intent Classifier State

Classifies user intent and takes conditional actions based on the classification.

```yaml
classify_user_intent:
  type: "intent_classifier"
  temperature: 0.1
  allowed_tools: [""]  # Usually no tools for classification

  intent_prompt: |
    The user said: "{user_input}"

    Classify their intent as:
    1. OPTION_A - Description
    2. OPTION_B - Description

    Respond with only: OPTION_A or OPTION_B

  intent_actions:
    OPTION_A:
      response: "Optional message to user"
      next_state: "state_for_option_a"
      data_storage:
        field_name: value

    OPTION_B:
      prompt: |
        Optional: Use LLM to generate response
        User said: {user_input}
      next_state: "state_for_option_b"
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | State type identifier | `"intent_classifier"` |
| `intent_prompt` | LLM instruction to classify user intent | `"Classify their intent as..."` |
| `intent_actions` | Map of intent names to action configurations | See example above |

#### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `temperature` | Controls classification randomness (0.0-1.0). | `0.7` |
| `allowed_tools` | Array of tool names (usually `[""]` for classification). | Unrestricted |
| `uses_tools` | Set to `"No"` to disable all tools. | Tools enabled |
| `uses_mcp_tools` | Set to `"No"` to disable MCP tools. | MCP tools enabled |

#### Intent Actions

Each intent in `intent_actions` can specify:

| Field | Description | Required |
|-------|-------------|----------|
| `next_state` | State to transition to | Yes |
| `response` | Static message to send to user | No |
| `prompt` | LLM prompt to generate dynamic response | No |
| `data_storage` | Fields to update with values | No |
| `allowed_tools` | Tools available if using `prompt` (action-level override) | No |
| `uses_tools` | Set to `"No"` to disable tools for this action's prompt (action-level override) | No |
| `uses_mcp_tools` | Set to `"No"` to disable MCP tools for this action's prompt (action-level override) | No |

**Notes:**
1. Use either `response` or `prompt`, but not both
2. Tool configuration (`allowed_tools`, `uses_tools`, `uses_mcp_tools`) can be set at both:
   - **State level**: Applies to intent classification and all actions (as default)
   - **Action level**: Overrides state-level settings for that specific action's prompt

### 4. Terminal State

Marks conversation end with optional reset behavior.

```yaml
end:
  type: "terminal"
  reset_behavior:
    reset_state: "initial_state_name"
    clear_data: ["messages", "current_state", "field1", "field2"]
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | State type identifier | `"terminal"` |

#### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `reset_behavior` | Configuration for resetting state after conversation ends | None |

#### Reset Behavior

When `reset_behavior` is specified, it supports:

| Field | Description | Example |
|-------|-------------|---------|
| `reset_state` | State to return to for next conversation | `"greet_and_identify_need"` |
| `clear_data` | Array of field names to clear | `["messages", "employee_info"]` |

### 5. LLM Validator State

Validates user input using LLM-based validation with conversation context.

```yaml
validate_laptop_selection:
  type: "llm_validator"
  temperature: 0.3
  validation_prompt: |
    The user selected: "{user_input}"
    Based on the available laptop options shown earlier, is this a valid selection?
    Respond with your validation assessment.

  success_validation_prompt: |
    LLM response: "{llm_response}"
    Does this indicate a VALID selection? Respond with VALID or INVALID.

  data_storage:
    selected_laptop: "user_input"

  transitions:
    valid: "confirm_selection"
    invalid: "waiting_laptop_selection"
```

#### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | State type identifier | `"llm_validator"` |
| `validation_prompt` | LLM prompt to validate user input with conversation context | See example |
| `success_validation_prompt` | LLM prompt to determine if validation passed (VALID/INVALID) | See example |
| `transitions` | Maps validation results to next states (must include `valid` and `invalid` keys) | See example |

#### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `temperature` | Controls validation randomness (0.0-1.0). | `0.3` |
| `allowed_tools` | Array of tool names (usually `[""]` for validation). | Unrestricted |
| `uses_tools` | Set to `"No"` to disable all tools. | Tools enabled |
| `uses_mcp_tools` | Set to `"No"` to disable MCP tools. | MCP tools enabled |
| `data_storage` | Map field names to `"user_input"` to store user's input in state fields. | None |

**Notes:**
1. The validator uses full conversation context. The `validation_prompt` gets conversation history plus the validation instructions. The `success_validation_prompt` evaluates the validation response to determine VALID or INVALID.
2. For `data_storage`, only `"user_input"` is supported as the source value (unlike `llm_processor` which supports `"llm_response"`).

## Response Analysis

Trigger actions based on LLM output patterns:

```yaml
classify_user_intent:
  type: "llm_processor"
  prompt: |
    Classify as: LAPTOP_REFRESH, EMAIL_CHANGE, or OTHER

  response_analysis:
    conditions:
      - name: "laptop_refresh"
        trigger_phrases: ["LAPTOP_REFRESH"]
        exclude_phrases: ["NOT_LAPTOP"]
        actions:
          - type: "add_message"
            message: "laptop-refresh"
          - type: "transition"
            target: "end"

      - name: "email_change"
        trigger_phrases: ["EMAIL_CHANGE"]
        actions:
          - type: "set_field"
            field_name: "request_type"
            value: "email"
          - type: "transition"
            target: "handle_email_change"

    default_transition: "handle_other_request"
```

**Response Analysis Parameters:**

| Parameter | Description | Required |
|-----------|-------------|----------|
| `conditions` | Array of condition objects to evaluate | No |
| `default_transition` | State to transition to if no conditions match | Yes |

**Condition Parameters:**

| Parameter | Description | Required |
|-----------|-------------|----------|
| `name` | Descriptive name for this condition | Yes |
| `trigger_phrases` | Array of phrases that must be present in response | Yes |
| `exclude_phrases` | Array of phrases that, if present, prevent this condition from matching | No |
| `actions` | Array of actions to execute when condition matches | Yes |

**Note:** Conditions are evaluated in order. If a response contains `trigger_phrases` but also contains any `exclude_phrases`, the condition is skipped.

### Action Types

#### 1. `add_message`
Send a message to the user.

```yaml
- type: "add_message"
  message: "Your message here with {field} interpolation"
```

#### 2. `transition`
Move to another state.

```yaml
- type: "transition"
  target: "next_state_name"
```

#### 3. `set_field`
Update a business field value.

```yaml
- type: "set_field"
  field_name: "eligibility_status"
  value: "ELIGIBLE"
```

#### 4. `extract_data`
Extract data from response or user input using regex patterns.

```yaml
- type: "extract_data"
  pattern: "laptop model: (.*)"
  field_name: "extracted_model"
  source: "response"  # or "last_user_message"
```

**Parameters:**
- `pattern`: Regular expression pattern (captured group 1 is stored, or full match if no groups)
- `field_name`: State field to store extracted value
- `source`: `"response"` (LLM response) or `"last_user_message"` (user input)

#### 5. `check_correction`
Check if a correction is needed based on additional phrases in the response.

```yaml
- type: "check_correction"
  correction_phrases: ["error", "invalid"]
  correction_message: "I noticed an issue: {field}"
```

**Parameters:**
- `correction_phrases`: Array of phrases indicating a correction is needed
- `correction_message`: Message to add if correction phrases found (supports field interpolation)

## Prompt Variable Interpolation

Reference data in prompts using curly braces:

```yaml
prompt: |
  Employee info: {employee_info.response}
  User said: {last_user_message}
  User input: {user_input}
  Selected laptop: {selected_laptop}
  Status: {eligibility_status}
```

### Available Variables

**Business Fields:**
- **`{field_name.response}`**: LLM response stored in field (e.g., `{employee_info.response}`)
- **`{field_name}`**: Direct field value (e.g., `{eligibility_status}`)

**Computed Variables:**
- **`{last_user_message}`**: Most recent user input from conversation history
- **`{user_input}`**: Current user message (available in intent classifiers and validators)
- **`{conversation_history}`**: Full conversation formatted as "User: ...\nAssistant: ...\n..."
- **`{authoritative_user_id}`**: The authenticated user's ID (if provided to the session)
- **`{llm_response}`**: LLM response (available in `success_validation_prompt` for validators)

**System Fields:**
- **`messages`**: Conversation message history (auto-managed, not typically referenced in prompts)
- **`current_state`**: Current state name (auto-managed)

**Escaping:**
- Use `{{` and `}}` to output literal braces: `{{example}}` renders as `{example}`

## Data Storage

Store LLM outputs in business fields:

```yaml
lookup_employee:
  type: "llm_processor"
  prompt: |
    Get employee info using get_employee_laptop_info tool.

  data_storage:
    employee_info: "llm_response"  # Stores entire LLM response
```

Access stored data in later states:
```yaml
check_eligibility:
  type: "llm_processor"
  prompt: |
    Based on this employee info: {employee_info.response}
    Check their eligibility.
```
