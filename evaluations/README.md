# Conversation Evaluation Framework

A comprehensive DeepEval-based evaluation system for testing and validating conversational AI agents, specifically designed for laptop refresh workflows and IT support scenarios.

## Overview

This framework provides end-to-end evaluation capabilities including:
- **Live Agent Testing**: Execute predefined conversation flows against deployed agents
- **Conversation Generation**: Create synthetic test conversations for comprehensive coverage
- **Metrics-Based Evaluation**: Apply business-specific metrics to assess agent performance
- **Pipeline Orchestration**: Automated execution of the complete evaluation workflow

## Quick Start

### Prerequisites

- Python 3.10+
- OpenShift CLI (`oc`) configured and authenticated
- Deployed self-service agent in OpenShift
- LLM API access (OpenAI-compatible endpoint)

### Installation

Install the evaluation framework and its dependencies:

```bash
# Basic installation (includes deepeval and openai)
pip install -e .

# Development installation with testing tools
pip install -e ".[dev]"

# Add additional LLM providers if needed
pip install -e ".[llm-extra]"

# Full installation with all optional enhancements
pip install -e ".[all]"
```

### Environment Variables

```bash
export LLM_API_TOKEN="your-api-token"
export LLM_URL="https://your-llm-endpoint"
export LLM_ID="your-model-id"  # Optional
```

### Run Complete Evaluation Pipeline

```bash
# Run full pipeline with defaults (20 generated conversations)
python evaluate.py

# Generate more conversations for thorough testing
python evaluate.py --num-conversations 50 --max-turns 30

# With custom timeout
python evaluate.py --timeout 900
```

## Components

### 1. Pipeline Orchestrator (`evaluate.py`)

Master script that coordinates the complete evaluation workflow:

```bash
python evaluate.py [options]
```

**Options:**
- `-n, --num-conversations`: Number of conversations to generate (default: 20)
- `--max-turns`: Maximum turns per conversation (default: 20)
- `--timeout`: Script execution timeout in seconds (default: 600)

**Pipeline Steps:**
1. Clean up previous generated files
2. Execute predefined conversation flows
3. Generate additional test conversations
4. Run comprehensive evaluation with metrics

### 2. Live Agent Testing (`run_conversations.py`)

Executes predefined conversation templates against live deployed agents:

```bash
python run_conversations.py
```

**Features:**
- Reads conversation templates from `conversations_config/conversations/`
- Connects to deployed agent via OpenShift
- Captures real agent responses
- Saves complete conversations to `results/conversation_results/`

**Template Format:**
```json
[
  {"role": "user", "content": "I need help with my laptop"},
  {"role": "user", "content": "My employee ID is 1234"},
  {"role": "user", "content": "Yes, I'd like to proceed"}
]
```

### 3. Conversation Generation (`generator.py`)

Creates synthetic conversations for comprehensive testing:

```bash
python generator.py [num_conversations] [options]
```

**Options:**
- `--max-turns`: Maximum conversation turns (default: 30)
- `--api-endpoint`: Custom LLM endpoint
- `--api-key`: API key override

**Features:**
- Generates realistic laptop refresh scenarios
- Configurable conversation patterns
- Integration with asset manager context
- Outputs timestamped conversation files

### 4. Evaluation Engine (`deep_eval.py`)

Comprehensive conversation evaluation with business metrics:

```bash
python deep_eval.py [options]
```

**Options:**
- `--results-dir`: Input conversations directory
- `--output-dir`: Evaluation results directory
- `--context-dir`: Additional context files directory
- `--api-endpoint`: Custom evaluation LLM endpoint

**Evaluation Metrics:**
- **Information Gathering**: Employee ID collection, current laptop details
- **Policy Compliance**: Laptop refresh eligibility, warranty validation
- **Option Presentation**: Location-based laptop options, specifications
- **Process Completion**: End-to-end workflow completion
- **User Experience**: Helpfulness, clarity, professionalism
- **Flow Termination**: Proper conversation ending with DONEDONEDONE or ticket number
- **Ticket Validation**: ServiceNow ticket format compliance (INC prefix)

## Directory Structure

```
evaluations/
├── README.md                          # This file
├── evaluate.py                        # Pipeline orchestrator
├── run_conversations.py               # Live agent testing
├── generator.py                       # Conversation generation
├── deep_eval.py                      # Evaluation engine
├── helpers/                          # Utility modules
│   ├── run_conversation_flow.py      # OpenShift integration
│   ├── openshift_chat_client.py      # Chat client implementation
│   ├── custom_llm.py                 # LLM integration
│   ├── deep_eval_summary.py          # Results reporting
│   ├── extract_deepeval_metrics.py   # Metrics processing
│   ├── load_conversation_context.py  # Context management
│   └── copy_context.py               # Context utilities
├── conversations_config/             # Conversation templates
│   ├── conversations/                # Predefined flow templates
│   ├── default_context/              # Default context files
│   └── conversation_context/         # Per-conversation context
└── results/                          # Output directories
    ├── conversation_results/         # Generated conversations
    └── deep_eval_results/           # Evaluation reports
```

## Configuration

### Conversation Templates

Place conversation templates in `conversations_config/conversations/`:

```json
[
  {"role": "user", "content": "Hello, I need help with my laptop"},
  {"role": "user", "content": "My employee ID is 5678"},
  {"role": "user", "content": "Yes, please show me the options"},
  {"role": "user", "content": "I'll take the MacBook Pro"},
  {"role": "user", "content": "Yes, please create the ticket"}
]
```

### Context Files

Add context for specific conversations in `conversations_config/conversation_context/`:
- Files should match conversation names
- Provides additional context for evaluation

### Results

#### Conversation Results (`results/conversation_results/`)
- Complete conversation transcripts in JSON format
- Both predefined flows and generated conversations
- Timestamped files for tracking

#### Evaluation Results (`results/deep_eval_results/`)
- Individual conversation evaluations (`deepeval_*.json`)
- Combined results (`deepeval_all_results.json`)
- Comprehensive metrics and scoring

## Error Handling

The framework includes robust error handling:

- **LLM Failures**: Individual evaluation failures don't stop the pipeline
- **Connection Issues**: Graceful handling of network problems
- **Timeout Management**: Configurable timeouts for long-running operations
- **Detailed Logging**: Comprehensive logs for debugging

## Customization

### Adding New Metrics

Extend `_create_laptop_refresh_metrics()` in `deep_eval.py`:

```python
ConversationalGEval(
    name="Custom Metric",
    threshold=0.8,
    evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
    evaluation_steps=[
        "Check for custom behavior",
        "Validate custom requirements"
    ],
    **model_kwargs,
)
```

### Custom LLM Integration

Modify `custom_llm.py` to support additional LLM providers or adjust parameters:

```python
# Adjust token limits
max_tokens=16000

# Modify temperature for evaluation consistency
temperature=0.1
```
