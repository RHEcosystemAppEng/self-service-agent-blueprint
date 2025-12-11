# Component Guide

This guide provides a comprehensive overview of all components in the Self-Service Agent system, organized into reusable core platform components and use-case-specific components.

## Overview

The quickstart consists of reusable **core platform components** and **use-case-specific components** (demonstrated through the laptop refresh example). Core components work across any IT process without modification, while use-case components show how to customize for specific workflows.

## Core Platform Components (Reusable Across Use Cases)

### Request Manager

**Purpose:** Central orchestrator that normalizes multi-channel requests and manages session state.

**Key Capabilities:**
- **Normalization:** Transforms diverse inputs (Slack messages, HTTP calls, CLI commands) into standardized internal format containing user message, identifier, integration type, and session context
- **Session Management:** Maintains conversational state across interactions by persisting sessions in PostgreSQL with conversation history, user metadata, and routing information

**Documentation:** See `request-manager/README.md` for detailed implementation

---

### Agent Service

**Purpose:** Mediates communication with agents and routing between them.

**Key Capabilities:**
- **Agent Orchestration:** Routes requests to appropriate agents (routing agent → specialist agents), managing handoffs and conversation context
- **Configuration-Driven:** Uses agents configured via YAML files in agent-service
- **Generic Design:** All domain logic comes from agent configurations—no hardcoded use-case behavior

**Documentation:** See `agent-service/README.md` for LlamaStack integration details

---

### Integration Dispatcher

**Purpose:** Multi-channel delivery hub that sends/receives messages through various communication channels.

**Key Capabilities:**
- **Channel Handlers:** Registry of handlers for Slack, Email, SMS, webhooks—each handles channel-specific protocols and formatting
- **Bidirectional Communication:** Implements webhook endpoints (e.g., Slack events), verifies signatures, extracts messages, forwards to Request Manager
- **Extensible Architecture:** Add custom channels (Teams, mobile apps) by implementing new handlers without core logic changes

**Documentation:** See [Integration Guide](INTEGRATION_GUIDE.md) for building custom integrations

---

### Mock Eventing Service

**Purpose:** Lightweight service that mimics Knative broker behavior for testing event-driven flows without complex infrastructure.

**Key Capabilities:**
- **Event Routing:** Accepts CloudEvents via HTTP, applies routing rules, forwards to destination services—identical protocols to production
- **In-Memory Configuration:** Routes event types (`agent.request` → Agent Service, `integration.delivery` → Integration Dispatcher)
- **Fast Iteration:** Instant startup, minimal resources, easy debugging—ideal for CI/CD pipelines and local development

**Documentation:** See [Deployment Mode Guide](DEPLOYMENT_MODE_GUIDE.md) for testing vs production modes

---

### Shared Libraries

**Purpose:** Foundational libraries ensuring consistency across all services through centralized data models and client implementations.

**shared-models:**
- **Database Schema:** SQLAlchemy models for database tables—single source of truth across all services
- **Pydantic Schemas:** Request/response validation with type safety and automatic serialization
- **Alembic Migrations:** Schema evolution management without manual SQL scripts

**shared-clients:**
- **HTTP Clients:** For external API access (RequestManagerClient for user-facing APIs)

**Documentation:** See `shared-models/README.md` and `shared-clients/README.md`

---

### Communication Integrations

**Purpose:** Connect agents to communication channels where users interact with the system.

**Communication Channels:**
- **Slack**: Real-time conversations in Slack workspace
- **Email**: Asynchronous notifications and updates
- **API/CLI**: Programmatic access and automation

**Key Capabilities:**
- Meet users where they work—no additional tools required
- Support multiple channels simultaneously (Slack conversation, email confirmations)
- Fully reusable across all use cases
- Extensible architecture for custom channels (Teams, mobile apps)

**Documentation:**
- [Slack Setup Guide](SLACK_SETUP.md)
- [Email Setup Guide](EMAIL_SETUP.md)
- [Integration Guide](INTEGRATION_GUIDE.md)

---

### Observability

**Purpose:** Monitor system behavior, track performance, and troubleshoot production issues.

**Key Capabilities:**
- **Distributed Tracing**: OpenTelemetry + Jaeger for request lifecycle visibility across all services
- **Performance Monitoring**: Track agent response latency, tool call timing, knowledge base retrieval performance
- **Error Tracking**: Debug failed integrations, conversation routing issues, ticket creation errors
- **Business KPIs**: Measure completion rates, user satisfaction, end-to-end request timing

**Integration:** Works with OpenShift observability stack—unified monitoring across platform components and existing infrastructure

**Reusability:** Infrastructure works for any use case without changes—add custom metrics for specific KPIs (PIA completion, RFP quality, etc.)

**Documentation:** See [Tracing Implementation](../docs/TRACING_IMPLEMENTATION.md)

---

### Evaluation Framework

**Purpose:** DeepEval-based testing system that validates agent behavior against business requirements and quality metrics.

**Key Capabilities:**
- **Conversation Execution**: Run predefined and generated conversation flows against deployed agents
- **Synthetic Generation**: Create varied test scenarios to exercise edge cases and diverse user inputs
- **Custom Metrics**: Define business-specific evaluation criteria using ConversationalGEval
- **Standard Metrics**: Built-in DeepEval metrics (Turn Relevancy, Role Adherence, Conversation Completeness)
- **Pipeline Automation**: Complete evaluation workflow from execution through reporting

**Why It Matters:**
- Validates business requirements before deployment
- Catches regressions when updating prompts or models
- Provides metrics for continuous improvement
- Validates compliance with policies and procedures
- Addresses non-deterministic nature of LLM responses

**Architecture:**
- **Conversation Flows**: JSON files defining turn-by-turn interactions
- **Metrics Configuration**: Python-based metric definitions in `get_deepeval_metrics.py`
- **Evaluation Engine**: DeepEval library for metric assessment
- **Results Storage**: JSON output with scores, reasons, and pass/fail status

**Reusability:** Framework structure (execution, generation, evaluation) is fully reusable—customize by defining use-case-specific conversation flows and metrics.

**Documentation:** See [Evaluations Guide](EVALUATIONS_GUIDE.md)

---

## Laptop Refresh Specific Components

These components build on the common components to implement the laptop refresh process. Apply the same patterns for your own use cases (PIA, RFP, etc.).

### MCP Servers

MCP servers allow agents to interact with external systems through standardized tools.

**Laptop Refresh MCP Server:**

**ServiceNow MCP (2 tools):**
- `get_employee_laptop_info`: Retrieves employee's laptop information including model, purchase date, age, warranty status, and employee details (name, location). Supports lookup by email address.
- `open_laptop_refresh_ticket`: Creates ServiceNow laptop refresh ticket. Returns ticket number and details.

**Implementation Details:**
- Supports both mock data (for testing/development) and real ServiceNow API integration
- Uses `AUTHORITATIVE_USER_ID` header for authenticated requests
- Mock data includes pre-defined employees with laptop information for evaluation testing

---

### Knowledge Bases

**Purpose:** Retrieval-Augmented Generation (RAG) system that grounds agent responses in authoritative organizational documents.

**Technical Implementation:** Documents chunked → converted to vector embeddings → stored in vector database → semantic search retrieves relevant chunks → provided to LLM as context

**Laptop Refresh Knowledge Base:**
- `refresh_policy.txt`: Eligibility criteria, approval process, special cases, policy rationale
- `NA_laptop_offerings.txt`: Available models for North America region with specifications, pricing, target user groups
- `EMEA_laptop_offerings.txt`: Available models for Europe, Middle East, and Africa region
- `APAC_laptop_offerings.txt`: Available models for Asia-Pacific region
- `LATAM_laptop_offerings.txt`: Available models for Latin America region

**Conversational Policy Explanation:** User asks "Why am I not eligible?" → Agent retrieves and explains specific unmet criteria

**Region-Specific Options:** User in EMEA region requests laptop options → Agent queries knowledge base for EMEA-specific offerings and presents only models available in that region with complete specifications

**Pattern:** Create directory under `agent-service/config/knowledge_bases/`, add .txt files, Agent Service handles chunking, embeddings, vector database creation, and LlamaStack registration.

#### Knowledge Base Updates

This quickstart uses an implementation where knowledge base documents are static text files loaded and ingested during agent service initialization. This approach allows you to get started quickly without complex infrastructure and is used as knowledge base creation and ongoing management is not the focus of this quickstart.

However, production deployments typically require a more sophisticated approach for updating knowledge bases as policies and documentation change. For production use cases, consider implementing a dedicated ingestion pipeline that can:
- Process updates from multiple source systems (SharePoint, Confluence, document management systems)
- Handle incremental updates without full redeployment
- Support various document formats (PDF, Word, HTML, etc.)
- Provide automated document processing and chunking
- Enable continuous synchronization of knowledge bases

For a complete ingestion pipeline architecture and implementation guidance, see the **[Ingestion Pipeline](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/ingestion-pipeline)** in the AI Architecture Charts repository. This architecture provides a production-ready approach to knowledge base management that can scale with your organization's needs. This quickstart could easily be adapted to use pre-existing knowledge bases managed by the ingestion pipeline by simply removing the knowledge base registration step from the init-job (`helm/templates/init-job.yaml`) and updating agent configurations to reference the existing vector store IDs created by your ingestion pipeline.

---

### Agents

**Purpose:** YAML configurations defining agent behavior, system instructions, accessible tools, and knowledge bases—registered with LlamaStack by Agent Service.

**Laptop Refresh Agent Architecture (Routing Pattern):**

#### Routing Agent

- **Role:** Front door—greets users, identifies intent, routes to appropriate specialist
- **Tools/Knowledge:** None—purely conversation and routing logic
- **Instructions:** Recognizes request types ("I need a new laptop" → laptop refresh specialist, "privacy assessment" → PIA specialist)
- **Extensibility:** Add specialists, update routing instructions—becomes conversational switchboard

#### Laptop Refresh Specialist Agent

- **Role:** Domain expert guiding laptop refresh process
- **Instructions:** Process flow (check eligibility, present options, create ticket), compliance requirements, interaction style
- **Tools:** ServiceNow tools (laptop information, ticket creation)
- **Knowledge Base:** `laptop-refresh` knowledge base for policy questions
- **Capabilities:** Queries knowledge base for policies, calls tools to check eligibility/retrieve options/create tickets

**Documentation:** See [Prompt Configuration Guide](PROMPT_CONFIGURATION_GUIDE.md)

---

### Evaluations

**Purpose:** Laptop refresh-specific conversation flows and metrics that validate the agent's ability to handle laptop refresh requests correctly.

**Predefined Conversation Flows:**
- **Success flow**: Complete laptop refresh request from greeting through ticket creation
- **Location**: `evaluations/conversations_config/conversations/`

**Evaluation Metrics** (in `get_deepeval_metrics.py`):

#### Standard Conversational Metrics
- **Turn Relevancy**: Measures relevance of assistant responses with multi-agent awareness
- **Role Adherence**: Evaluates adherence to agent roles with multi-agent routing support
- **Conversation Completeness**: Assesses conversation flow completeness with multi-agent routing support

#### Laptop Refresh Process Metrics
- **Information Gathering**: Evaluates collection of necessary laptop information
- **Policy Compliance**: Verifies correct application of 3-year laptop refresh policy
- **Option Presentation**: Assesses quality and clarity of laptop option presentation
- **Process Completion**: Validates complete flow (eligibility → options → selection → ticket creation)
- **User Experience**: Measures helpfulness, professionalism, and clarity throughout conversation

#### Quality Assurance Metrics
- **Flow Termination**: Validates proper conversation ending (ticket number or DONEDONEDONE marker)
- **Ticket Number Validation**: Confirms correct ServiceNow ticket format (REQ prefix)
- **Correct Eligibility Validation**: Verifies accurate 3-year policy timeframe statements
- **No Errors Reported**: Checks for system response problems or failures
- **Correct Laptop Options for User Location**: Validates all location-specific models are presented
- **Confirmation Before Ticket Creation**: Ensures agent requests user approval before creating ticket
- **Return to Router After Task Completion**: Verifies proper routing when user declines further assistance

**Documentation:** See [Evaluations Guide](EVALUATIONS_GUIDE.md)

---

## Customizing Components for Your Use Case

To adapt these components for your own use case:

1. **Keep Core Platform Components**: Request Manager, Agent Service, Integration Dispatcher, Mock Eventing, Shared Libraries, Observability, and Evaluation Framework work across all use cases without modification

2. **Customize Use-Case-Specific Components**:
   - **MCP Servers**: Build tools for your external systems (HR, compliance, document management)
   - **Knowledge Bases**: Add your policy documents, guidelines, templates
   - **Agents**: Configure routing and specialist agents for your workflow
   - **Evaluations**: Define conversation flows and metrics for your business requirements

3. **Follow Established Patterns**: The laptop refresh implementation demonstrates all patterns—use it as a reference when building your own use case

For detailed customization guidance, see [Customizing for your use case](../README.md#customizing-for-your-use-case) in the main README.
