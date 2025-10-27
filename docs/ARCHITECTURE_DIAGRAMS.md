# Self-Service Agent Architecture Flows

This document illustrates the two primary flow patterns in the self-service agent stack.

## Session Management Responsibilities

**Request Manager**: Manages request-level sessions for tracking user interactions across integrations (Slack, Email, CLI, etc.). Each session represents a conversation thread with a user and tracks request counts, user context, and integration-specific metadata.

**Agent Service**: Manages LlamaStack agent sessions for AI conversation continuity. Each LlamaStack session maintains the AI agent's conversation history and context for generating coherent responses.

## Flow 1: System-Initiated Events (Slack Only)

This flow handles inbound events and messages from Slack (the only integration that can receive incoming requests).

**Production Mode (Eventing Configuration):**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   External      │    │   Integration   │    │   Request       │
│   Systems       │───▶│   Dispatcher    │───▶│   Manager       │
│                 │    │                 │    │                 │
│ • Slack Events  │    │ • Event Handler │    │ • Normalize     │
│ • Slack Commands│    │ • Signature     │    │ • Validate      │
│ • Slack Actions │    │   Verification  │    │ • Publish Event │
│                 │    │ • User Context  │    │ • Return ID     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ HTTP Slack Events     │ HTTP Request          │ CloudEvent
         │ POST /slack/events    │ POST /api/v1/...      │ (request.created)
         │ POST /slack/commands  │                       │
         │                       │                       ▼
         ▼                       ▼                      ┌─────────────────┐
┌─────────────────┐    ┌─────────────────┐              │   Knative       │
│   Slack App     │    │   Database      │              │   Broker        │
│   Components    │    │                 │              │   (Kafka)       │
│                 │    │ • User Lookup   │              │                 │
│ • Message       │    │ • Session Data  │              │ • Event Routing │
│ • Interactive   │    │ • Integration   │              │ • Persistence   │
│ • Slash Cmd     │    │   Config        │              │ • Reliability   │
└─────────────────┘    └─────────────────┘              └─────────────────┘
                                                                  │
                                                                  │ CloudEvent
                                                                  │ (request.created)
                                                                  ▼
                       ┌─────────────────┐              ┌─────────────────┐
                       │   Knative       │              │   Agent         │
                       │   Trigger       │─────────────▶│   Service       │
                       │                 │              │                 │
                       │ • Event Filter  │              │ • AI Processing │
                       │ • Service       │              │ • LLM Calls     │
                       │   Binding       │              │ • Tool Usage    │
                       │                 │              │ • Response Gen  │
                       └─────────────────┘              └─────────────────┘
                                                                  │
                                                                  │ CloudEvent
                                                                  │ (response.ready)
                                                                  ▼
                       ┌─────────────────┐              ┌─────────────────┐
                       │   Integration   │◀─────────────│   Knative       │
                       │   Dispatcher    │              │   Trigger       │
                       │                 │              │                 │
                       │ • Route Back    │              │ • Event Filter  │
                       │   to Original   │              │ • Service       │
                       │   Integration   │              │   Binding       │
                       │ • Deliver       │              │                 │
                       └─────────────────┘              └─────────────────┘
                                │
                                │ Deliver Response
                                ▼
                       ┌─────────────────┐
                       │   Integration   │
                       │   Handlers      │
                       │                 │
                       │ • SLACK ←───────┼─── Back to Slack
                       │ • EMAIL         │
                       │ • WEBHOOK       │
                       │ • TEST          │
                       └─────────────────┘
```

---

## Flow 2: User-Initiated Requests (CLI/API/Web)

This flow handles requests initiated directly by users through command-line tools, APIs, web interfaces, or scripts.

**Production Mode (Eventing Configuration):**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   External      │    │   Request       │    │   Knative       │
│   Clients       │───▶│   Manager       │───▶│   Broker        │
│                 │    │                 │    │   (Kafka)       │
│ • CLI Tools     │    │ • Normalize     │    │                 │
│ • curl/API      │    │ • Validate      │    │ • Event Routing │
│ • Web UI        │    │ • Publish Event │    │ • Persistence   │
│ • Scripts       │    │ • Return ID     │    │ • Reliability   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ HTTP Request          │ CloudEvent            │ CloudEvent
         │ POST /api/v1/...      │ (request.created)     │ (request.created)
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Response      │    │   Database      │    │   Agent         │
│                 │    │                 │    │   Service       │
│ SYNC:           │    │ • Request Store │    │                 │
│ • 200 OK        │    │ • Session Data  │    │ • AI Processing │
│ • Complete      │    │ • User Config   │    │ • LLM Calls     │
│   Result        │    │ • Integration   │    │ • Tool Usage    │
│                 │    │   Settings      │    │ • Response Gen  │
│ ASYNC:          │    │                 │    │                 │
│ • 202 Accepted  │    │                 │    │                 │
│ • request_id    │    │                 │    │                 │
│ • session_id    │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                │                       │ CloudEvent
                                │                       │ (response.ready)
                                │                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Integration   │◀───│   Knative       │
                       │   Dispatcher    │    │   Trigger       │
                       │                 │    │                 │
                       │ • Route to      │    │ • Event Filter  │
                       │   Integration   │    │ • Service       │
                       │ • Handle        │    │   Binding       │
                       │   Delivery      │    │                 │
                       └─────────────────┘    └─────────────────┘
                                │
                   ┌────────────┴────────────┐
                   │                         │
                   ▼ (if integration_type)   ▼ (if polling)
          ┌─────────────────┐       ┌─────────────────┐
          │   Integration   │       │   Database      │
          │   Handlers      │       │   Storage       │
          │                 │       │                 │
          │ • SLACK         │       │ • Store Result  │
          │ • EMAIL         │       │ • Update Status │
          │ • WEBHOOK       │       │ • Available for │
          │ • TEST          │       │   API Polling   │
          └─────────────────┘       └─────────────────┘
                   │                         │
                   ▼                         ▼
          ┌─────────────────┐       ┌─────────────────┐
          │   Final         │       │   User Polls    │
          │   Delivery      │       │   for Result    │
          │                 │       │                 │
          │ • Slack DM      │       │ • GET /status   │
          │ • Email Inbox   │       │ • GET /result   │
          │ • Webhook POST  │       │ • API Response  │
          │ • Test Output   │       │                 │
          └─────────────────┘       └─────────────────┘
```

### Key Characteristics:
- **Entry Point**: Request Manager (HTTP API)
- **Use Cases**: CLI tools, scripts, web UIs, programmatic access
- **Flow**: Request → Normalize → Event → AI Processing → Integration Delivery
- **Response**: Immediate HTTP response with tracking IDs

### Response Patterns for Async Requests:

**Pattern A: Integration-Based Delivery (Shown Above)**
- User specifies `integration_type` in request (e.g., "slack", "email", "webhook")
- Response delivered through that integration channel
- User gets immediate tracking IDs, result delivered via integration

**Pattern B: Polling-Based Retrieval**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CLI/Script    │    │   Request       │    │   Database      │
│                 │───▶│   Manager       │───▶│                 │
│ • POST request  │    │                 │    │ • Store Result  │
│ • Get IDs       │    │ • Return IDs    │    │ • Update Status │
│ • Poll for      │    │ • GET /status   │    │ • Session Data  │
│   completion    │    │ • GET /result   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ 1. POST /api/v1/...   │                       │
         │ 2. 202 + IDs          │                       │
         │ 3. GET /status        │ Query Status          │
         │ 4. GET /result        │ Fetch Result          │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Final Result  │    │   Status/Result │    │   Agent         │
│                 │◀───│   Endpoints     │    │   Service       │
│ • Complete      │    │                 │    │                 │
│   Response      │    │ • /requests/    │    │ • Writes Result │
│ • Session Data  │    │   {id}/status   │    │   to Database   │
│ • Metadata      │    │ • /requests/    │    │ • Updates       │
│                 │    │   {id}/result   │    │   Status        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**When to Use Each Pattern:**
- **Integration Delivery**: When user wants result in Slack, email, or webhook
- **Polling**: When user wants to retrieve result programmatically via API

---

## Common Components

Both flows share these core components:

### **Communication Infrastructure**

**Production Mode (Eventing Configuration):**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kafka Broker  │    │   Triggers      │    │   CloudEvents   │
│                 │    │                 │    │                 │
│ • Event         │    │ • request.*     │    │ • Standard      │
│   Persistence   │    │ • response.*    │    │   Format        │
│ • Reliable      │    │ • Service       │    │ • Metadata      │
│   Delivery      │    │   Routing       │    │ • Tracing       │
│ • Scalability   │    │ • Filtering     │    │ • Versioning    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Integration Dispatcher: Outgoing Delivery Hub

The **Integration Dispatcher** is primarily responsible for **outgoing response delivery** to external systems. While it can receive Slack events, its main role is to deliver AI agent responses to users through various channels.

### **Primary Responsibilities:**

**1. Response Delivery Management**
- **Multi-channel delivery**: Slack, Email, SMS, Webhooks, Test
- **Delivery routing**: Routes responses to appropriate integration handlers
- **Retry logic**: Handles failed deliveries with configurable retry policies
- **Delivery status tracking**: Monitors success/failure of all deliveries

**2. Integration Handler Management**
- **SlackIntegrationHandler**: Delivers responses to Slack channels/DMs
- **EmailIntegrationHandler**: Delivers responses via SMTP
- **WebhookIntegrationHandler**: Delivers responses via HTTP POST
- **TestIntegrationHandler**: Delivers responses for testing/CI

**3. User Configuration Management**
- **Integration defaults**: System-wide default configurations
- **User overrides**: Custom configurations for specific users
- **Lazy configuration**: Applies defaults without database persistence
- **Priority-based delivery**: Delivers through highest priority channels first

### **Secondary Responsibilities:**

**4. Slack Event Processing (Incoming Only)**
- **Event handling**: Processes Slack events, mentions, commands
- **Signature verification**: Validates Slack request authenticity
- **Request forwarding**: Forwards Slack requests to Request Manager
- **Interactive components**: Handles Slack buttons, modals, etc.

### **Key Architecture Pattern:**

```
AI Agent Response → Integration Dispatcher → [Slack|Email|SMS|Webhook|Test] → User
```

The Integration Dispatcher acts as the **delivery gateway** ensuring responses reach users through their preferred communication channels while managing delivery reliability and user preferences.

---

### **Database Layer**
```
┌─────────────────┐
│   PostgreSQL    │
│   (pgvector)    │
│                 │
│ • Requests      │
│ • Sessions      │
│ • User Config   │
│ • Integration   │
│   Settings      │
│ • Vector Store  │
│ • Delivery Logs │
└─────────────────┘
```

### **Shared Libraries Architecture**
```
┌─────────────────┐    ┌─────────────────┐
│   shared-models │    │  shared-clients │
│                 │    │                 │
│ • Database      │    │ • HTTP Clients  │
│   Models        │    │ • Service       │
│ • Pydantic      │    │   Communication │
│   Schemas       │    │ • Unified API   │
│ • Enums &       │    │   Interface     │
│   Utilities     │    │ • Error         │
│ • Migration     │    │   Handling      │
│   Scripts       │    │ • Retry Logic   │
│ • CloudEvent    │    │ • Request       │
│   Utilities     │    │   Manager       │
│ • FastAPI       │    │   Client        │
│   Utilities     │    │ • Stream        │
│ • Health        │    │   Processor     │
│   Checkers      │    │                 │
│ • Logging       │    │                 │
│   Utilities     │    │                 │
└─────────────────┘    └─────────────────┘
         │                       │
         │ Used by all services  │ Used by all services
         │ for data models       │ for inter-service
         │ and database access   │ communication
         ▼                       ▼
┌─────────────────────────────────────────┐
│           All Services                  │
│                                         │
│ • agent-service                         │
│ • request-manager                       │
│ • integration-dispatcher                │
│ • mcp-servers                           │
└─────────────────────────────────────────┘
```

### **AI/Agent Layer**
```
┌─────────────────┐
│   Agent Service │
│                 │
│ • LlamaStack    │
│ • Tool Calling  │
│ • RAG Pipeline  │
│ • Context Mgmt  │
│ • Response Gen  │
│ • Session CRUD  │
│   (Centralized) │
└─────────────────┘
```

### **Communication Modes**

**Eventing-Based Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Eventing Architecture                   │
│                                                             │
│  ┌─────────────────┐              ┌─────────────────┐      │
│  │   Production    │              │   Development/  │      │
│  │   Mode          │              │   Testing Mode  │      │
│  │                 │              │                 │      │
│  │ • Knative       │              │ • Mock          │      │
│  │   Broker        │              │   Eventing      │      │
│  │ • CloudEvents   │              │ • CloudEvents   │      │
│  │ • Kafka         │              │ • In-Memory     │      │
│  │ • Triggers      │              │ • No Knative    │      │
│  │ • Scalable      │              │ • Simplified    │      │
│  └─────────────────┘              └─────────────────┘      │
│           │                               │                │
│           └───────────┬───────────────────┘                │
│                       │                                    │
│                       ▼                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Unified Request Processor                 │   │
│  │                                                     │   │
│  │ • CloudEvent Processing                             │   │
│  │ • Session Management                                │   │
│  │ • Agent Routing                                     │   │
│  │ • Response Handling                                 │   │
│  │ • Eventing-Based Communication                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### **Session Management Architecture**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Request       │    │   Agent         │    │   Integration   │
│   Manager       │───▶│   Service       │◀───│   Dispatcher    │
│                 │    │                 │    │                 │
│ • Request       │    │ • Session CRUD  │    │ • Session       │
│   Logging       │    │   Endpoints     │    │   Queries       │
│ • Event         │    │ • Database      │    │ • User Context  │
│   Deduplication │    │   Access        │    │ • Integration   │
│ • Request       │    │ • LlamaStack    │    │   Metadata      │
│   Tracking      │    │   Session Mgmt  │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ HTTP API Calls        │ Direct DB Access      │ HTTP API Calls
         │ (shared-clients)      │ (shared-models)       │ (shared-clients)
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                      │
│                                                             │
│ • RequestSession (Agent Service)                           │
│ • RequestLog (Request Manager)                             │
│ • ProcessedEvent (Request Manager)                         │
│ • User Config & Integration Settings                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Flow Comparison

| Aspect | System-Initiated Events | User-Initiated Requests |
|--------|----------------------|------------------------------|
| **Entry Point** | Slack Events (`/slack/*`) | HTTP API (`/api/v1/requests/*`) |
| **Initiator** | External system/integration | External client/user |
| **Response** | Delivered via same integration | HTTP response with IDs |
| **Use Cases** | Slack events, commands, interactions | CLI, scripts, web UI, API |
| **User Context** | Looked up from integration | Provided in request |
| **Session** | Linked to integration thread | New or specified |
| **Delivery** | Back to originating integration | Any configured integration |

Both flows converge at the Agent Service and use the same event-driven architecture for reliability and scalability.

---

## Key Architectural Improvements

### **1. Eventing-Based Communication**
- **CloudEvents Standard**: All inter-service communication uses CloudEvents for consistency
- **Dual Eventing Modes**: Mock eventing for development/testing, full Knative eventing for production
- **Consistent API**: Same request/response patterns across all communication modes
- **Production Mode**: Eventing with Knative brokers, Kafka, and triggers for scalability
- **Development/Testing Mode**: Mock eventing service for simplicity and debugging without Knative infrastructure

### **2. Centralized Session Management**
- **Single Source of Truth**: All session operations handled by Agent Service
- **HTTP API**: Session CRUD operations exposed via REST endpoints
- **Shared Clients**: Consistent HTTP client usage across all services
- **Database Separation**: Session data (Agent Service) vs Request logging (Request Manager)

### **3. Shared Libraries Architecture**
- **`shared-models`**: Common data models, schemas, and database utilities
- **`shared-clients`**: Centralized HTTP client implementations for inter-service communication
- **Consistent Naming**: All packages follow `self-service-agent-*` naming convention
- **Dependency Management**: Proper package dependencies and local path references

### **4. Service Responsibilities**
- **Agent Service**: AI processing, session management, LlamaStack integration
- **Request Manager**: Request logging, event deduplication, request tracking, session management
- **Integration Dispatcher**: **Outgoing response delivery**, integration defaults, user overrides, Slack event processing
- **Shared Libraries**: Common functionality and inter-service communication

### **5. Benefits**
- **Maintainability**: Single codebase for both communication modes
- **Consistency**: Unified API patterns and error handling
- **Scalability**: Eventing for high-throughput, HTTP for direct integration
- **Reliability**: Centralized session management with proper error handling
- **Developer Experience**: Clear separation of concerns and shared utilities
