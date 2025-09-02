# Self-Service Agent Architecture Flows

This document illustrates the two primary flow patterns in the self-service agent stack.

## Flow 1: System-Initiated Events (Slack/Webhooks/Integrations)

This flow handles inbound events and messages from external systems like Slack, webhooks, and other integrated tools.

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   External      │    │   Integration   │    │   Request       │
│   Systems       │───▶│   Dispatcher    │───▶│   Manager       │
│                 │    │                 │    │                 │
│ • Slack Events  │    │ • Event Handler │    │ • Normalize     │
│ • Webhooks      │    │ • Signature     │    │ • Validate      │
│ • Tool Events   │    │   Verification  │    │ • Publish Event │
│ • Integrations  │    │ • User Context  │    │ • Return ID     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ HTTP Webhook          │ HTTP Request          │ CloudEvent
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

### Key Characteristics:
- **Entry Point**: Integration Dispatcher (Webhook endpoints)
- **Use Cases**: Slack messages, external webhooks, tool integrations
- **Flow**: External Event → Handler → Request Manager → AI Processing → Back to Integration
- **Response**: Delivered back through the same integration channel

---

## Flow 2: User-Initiated Requests (CLI/API/Web)

This flow handles requests initiated directly by users through command-line tools, APIs, web interfaces, or scripts.

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

### **Knative Eventing Infrastructure**
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
└─────────────────┘
```

---

## Flow Comparison

| Aspect | System-Initiated Events | User-Initiated Requests |
|--------|----------------------|------------------------------|
| **Entry Point** | Webhook (`/slack/*`, `/webhook/*`) | HTTP API (`/api/v1/requests/*`) |
| **Initiator** | External system/integration | External client/user |
| **Response** | Delivered via same integration | HTTP response with IDs |
| **Use Cases** | Slack, webhooks, tool events | CLI, scripts, web UI, API |
| **User Context** | Looked up from integration | Provided in request |
| **Session** | Linked to integration thread | New or specified |
| **Delivery** | Back to originating integration | Any configured integration |

Both flows converge at the Agent Service and use the same event-driven architecture for reliability and scalability.
