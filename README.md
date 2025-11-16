# Self-Service Agent Quickstart

## Table of Contents

1. [Introduction](#1-introduction)
   - [Who Is This For?](#11-who-is-this-for)
   - [The Business Case for AI-Driven IT Self-Service](#12-the-business-case-for-ai-driven-it-self-service)
   - [Example Use Cases](#13-example-use-cases)
   - [What This Quickstart Provides](#14-what-this-quickstart-provides)
   - [What You'll Build](#15-what-youll-build)
   - [Architecture Overview](#16-architecture-overview)
   - [Project Structure](#17-project-structure)
   - [Laptop Refresh Implementation](#18-laptop-refresh-implementation)
   - [Customizing for Your Use Case](#19-customizing-for-your-use-case)

2. [Prerequisites](#2-prerequisites)
   - [Required Tools](#21-required-tools)
   - [Environment Requirements](#22-environment-requirements)
   - [Access Requirements](#23-access-requirements)
   - [Knowledge Prerequisites](#24-knowledge-prerequisites)
   - [Time Estimate](#25-time-estimate)

3. [Architecture & Deployment Modes](#3-architecture--deployment-modes)
   - [Deployment Modes](#31-deployment-modes)
   - [Request Flow](#32-request-flow)

4. [Component Overview](#4-component-overview)
   - [Core Platform Components](#41-core-platform-components-reusable-across-use-cases)
   - [Laptop Refresh Specific Components](#42-laptop-refresh-specific-components)

5. [Hands-On Quickstart](#5-hands-on-quickstart)
   - [Deploy to OpenShift](#51-deploy-to-openshift)
   - [Interact with the CLI](#52-interact-with-the-cli)
  - [Integration with Slack (Optional)](#53-integration-with-slack-optional)
  - [Integration with Real ServiceNow (Optional)](#54-integration-with-real-servicenow-optional)
  - [Integration with Email (Optional)](#55-integration-with-email-optional)
  - [Setting up Safety Shields (Optional)](#56-setting-up-safety-shields-optional)
  - [Run Evaluations](#57-run-evaluations)
  - [Follow the Flow with Observability](#58-follow-the-flow-with-observability)

6. [Performance & Scaling](#6-performance--scaling)

7. [Going Deeper: Component Documentation](#7-going-deeper-component-documentation)
   - [Core Platform](#71-core-platform)
   - [Agent Configuration](#72-agent-configuration)
   - [External Integrations](#73-external-integrations)
   - [Quality & Operations](#74-quality--operations)

8. [Customizing for Your Use Case](#8-customizing-for-your-use-case)
   - [Planning Your Use Case](#81-planning-your-use-case)

9. [Next Steps and Additional Resources](#9-next-steps-and-additional-resources)
   - [What You've Accomplished](#91-what-youve-accomplished)
   - [Recommended Next Steps](#92-recommended-next-steps)

---

## 1. INTRODUCTION

### 1.1 Who Is This For?

This quickstart guide is designed for:

- **IT teams** implementing AI-driven self-service solutions
- **DevOps engineers** deploying agent-based systems
- **Solution architects** evaluating AI automation platforms
- **Organizations** looking to streamline IT processes with generative AI

### 1.2 The Business Case for AI-Driven IT Self-Service

Many organizations are working to support IT processes through generative AI based self-service implementations. IT teams at Red Hat have already started on this journey. The team building this quickstart met with those teams to incorporate the lessons learned into this guide.

The key value propositions for implementing IT processes with generative AI include:

* **Reduced employee time to complete common requests.** The system helps employees create their requests by helping them understand the options and required information for the request and helps employees submit those requests once they are ready.
* **Higher compliance to process standards.** Requests will be more complete and aligned with process standards. This will reduce the need to contact the requesting employee for additional information and reduce time and effort to review and complete requests.
* **Fewer rejected requests due to missing/incorrect information.** Rejected requests are frustrating for employees and leads to lower employee satisfaction. Avoiding request rejection and reducing back and forth on requests will improve employee satisfaction.
* **Shorter time to close a ticket.** The system helps tickets to close faster, improving throughput and reducing ticket idle time.

### 1.3 Example Use Cases

IT processes that are suitable for automation with generative AI include:

* Laptop refresh requests
* Privacy Impact Assessment (PIA)
* RFP generation
* Access request processing
* Software license requests

### 1.4 What This Quickstart Provides

This quickstart provides the framework, components and knowledge to accelerate your journey to deploying generative AI based self-service implementations. Many AI based IT process implementations should be able to share common components within an enterprise. The addition of agent configuration files, along with additional tools, knowledge bases, and evaluations, completes the implementation for a specific use case. Often no code changes to the common components will be required to add support for an additional use case.

### 1.5 What You'll Build

The quickstart provides implementations of the common components along with the process specific pieces needed to support the laptop refresh IT process as a concrete implementation.

**Time to complete:** 30-60 minutes (depending on deployment mode)

By the end of this quickstart, you will have:
- A fully functional AI agent system deployed
- A working laptop refresh agent with knowledge bases and tools
- Completed evaluation runs demonstrating agent quality
- (Optional) Slack integration
- (Optional) ServiceNow integration for real ticket creation
- Understanding of how to customize for your own use cases

### 1.6 Architecture Overview

The self-service agent quickstart provides a reusable platform for building AI-driven IT processes:

![Common Platform Architecture](docs/pictures/top-level-architecture.png)

In addition to the base components, the quickstart includes an evaluation framework and integration with OpenTelemetry support in OpenShift for observability.

**Why Evaluations Matter:**

Generative AI agents are non-deterministic by nature, meaning their responses can vary across conversations even with identical inputs. This makes traditional software testing approaches insufficient. The evaluation framework addresses this challenge by providing capabilities that are crucial for successfully developing and iterating on agentic IT process implementations. The framework validates business-specific requirements—such as policy compliance and information gathering—ensuring agents meet quality standards before deployment and catch regressions during updates.

**Why Observability Matters:**

Agentic systems involve complex interactions between multiple components—routing agents, specialist agents, knowledge bases, MCP servers, and external systems—making production debugging challenging without proper visibility. The OpenTelemetry integration provides distributed tracing across the entire request lifecycle, enabling teams to understand how requests flow through the system, identify performance bottlenecks, and diagnose issues in production. This visibility is essential for monitoring agent handoffs between routing and specialist agents, debugging failed external system integrations, and understanding user interaction patterns. By integrating with OpenShift's observability stack, teams gain unified monitoring across all platform components alongside their existing infrastructure metrics.

**Key Request Flow:**
1. User initiates request through any communications channel (Slack, Email, API, Web)
2. Request Manager validates request and routes to routing agent
3. Routing agent interacts with the user to find out what the user needs
4. Routing agent hands session off to specialist agent to complete the request
5. Specialist agent interacts with user to complete request using available knowledge bases and MCP servers

### 1.7 Project Structure

The repository is organized into the following key directories:

**Core Services:**
- **`agent-service/`** - AI agent processing service with knowledge base management and LangGraph state machine
- **`request-manager/`** - Request routing, session management, and unified communication processing
- **`integration-dispatcher/`** - Multi-channel delivery (Slack, Email, Webhooks)
- **`mock-eventing-service/`** - Lightweight mock service for testing without Knative infrastructure

**MCP Servers:**
- **`mcp-servers/snow/`** - ServiceNow integration MCP server

**Shared Libraries:**
- **`shared-models/`** - Database models, Pydantic schemas, and Alembic migrations
- **`shared-clients/`** - Centralized HTTP client libraries for inter-service communication

**Evaluation & Testing:**
- **`evaluations/`** - Evaluation framework with conversation flows and metrics
- **`test/`** - Testing utilities and scripts

**Infrastructure & Configuration:**
- **`helm/`** - Kubernetes Helm charts for OpenShift deployment
- **`agent-service/config/`** - Agent configurations, knowledge bases, and LangGraph prompts
- **`tracing-config/`** - OpenTelemetry configuration for observability
- **`scripts/`** - CI/CD and container build scripts

**Documentation:**
- **`docs/`** - Additional guides and documentation resources

For detailed information on each component, see [Section 4: Component Overview](#4-component-overview).

### 1.8 Laptop Refresh Implementation

The laptop refresh use case is implemented by adding the following components:

1. MCP server integrated with ServiceNow that can:
   * retrieve existing laptop information for an employee
   * submit a refresh request on behalf of an employee
2. Laptop refresh knowledge base that includes laptop refresh policy and available
   laptop options per region
3. Routing agent that knows how to route to the laptop refresh agent
4. Laptop refresh agent configured with prompts for the refresh process
5. A set of evaluations specific to the laptop refresh IT process

**User Authentication:**

The user's email address is used as the authoritative identifier for the user. Communication channels like Slack and email provide pre-authenticated user identities, eliminating the need for separate authentication. The email address obtained from these channels is passed through the Request Manager to MCP servers, which use it to perform operations on behalf of the user—such as retrieving employee information and submitting refresh requests.

The ServiceNow MCP server authenticates to the ServiceNow backend using a service account, following standard ServiceNow integration patterns.

**Example Conversation: Laptop Refresh Process**

**User:** Hi, I'm looking to refresh my laptop, can you please guide me through the process and show me the available options?

**Agent:** Your laptop, an EliteBook 840 G7, was purchased on 2019-05-12 and is currently 6 years and 5 months old. The company's laptop refresh policy states that standard laptops will be refreshed every 3 years from the date of issuance. Since your laptop is older than 3 years, you are eligible for a laptop refresh. Would you like to proceed with reviewing the available laptop options for your location?

**User:** Yes, I'd like to proceed with reviewing the available laptop options for my location.

**Agent:** Here are the available laptop options for your location (NA):

**1. Apple MacBook Air M3** (Code: apple_mac_book_air_m_3)
- Target User: General Office
- Cost: $1,199 USD
- Operating System: macOS
- Display: 13.6" (2560 x 1664)
- Processor: Apple M3
- Memory: 8 GB
- Storage: 256 GB SSD
- Weight: 2.7 lbs

**2. Apple MacBook Pro 14 M3 Pro** (Code: apple_mac_book_pro_14_m_3_pro)
- Target User: Developers
- Cost: $1,999 USD
- Operating System: macOS
- Display: 14.2" (3024 x 1964)
- Processor: Apple M3 Pro
- Memory: 18 GB
- Storage: 512 GB SSD
- Weight: 3.5 lbs

**3. Lenovo ThinkPad T14 Gen 5 Intel** (Code: lenovo_think_pad_t_14_gen_5_intel)
- Target User: General Office
- Cost: $1,399 USD
- Operating System: Windows 11 Pro
- Display: 14" (1920 x 1200)
- Processor: Intel Core i7-1555U
- Memory: 16 GB
- Storage: 512 GB SSD
- Weight: 3.2 lbs

**4. Lenovo ThinkPad P1 Gen 7** (Code: lenovo_think_pad_p_1_gen_7)
- Target User: Engineers
- Cost: $2,499 USD
- Operating System: Red Hat Linux
- Display: 16" (2560 x 1600)
- Processor: Intel Core i7-13800H
- Memory: 32 GB
- Storage: 1 TB SSD
- Graphics: NVIDIA RTX A1000
- Weight: 4.1 lbs

Please select one of the above options. Remember to consider your job role and requirements when making your selection.

**User:** I'd like to select option 1, the Apple MacBook Air M3, as it seems suitable for my general office needs.

**Agent:** You've selected the Apple MacBook Air M3. Would you like to proceed with the creation of a ServiceNow ticket for a laptop refresh?

**User:** Yes, please proceed with creating the ServiceNow ticket for the laptop refresh, and can you also let me know what information I need to provide for the ticket?

**Agent:** A ServiceNow ticket for a laptop refresh has been created for you. The ticket number is REQ3143724. Your request will be processed by the IT Hardware Team, and you will receive updates via email as the ticket progresses.

Is there anything else I can help you with?

### 1.9 Customizing for Your Use Case

To adapt this quickstart for your specific IT process:

- Replace laptop refresh agent with your specialist agent (e.g., PIA, RFP)
- Update the routing agent to be able to route to your new specialist agent
- Add MCP servers for your external systems
- Create knowledge base with your policies and documentation
- Build evaluation suite for your business metrics

---

## What's Next

Now that you understand the architecture and capabilities of the self-service agent quickstart, the next section will guide you through the prerequisites and setup steps needed to deploy the system on your OpenShift cluster.

---

## 2. PREREQUISITES

### 2.1 Required Tools

Before you begin, ensure you have:

* Python 3.12+ - Required for all services and components
* uv - Fast Python package installer (https://github.com/astral-sh/uv)
* Podman - Container runtime for building images
* Helm - Kubernetes package manager (for deployment)
* oc - OpenShift command line tool
* git - Version control
* make - Build automation (usually pre-installed on Linux/macOS)

### 2.2 Environment Requirements

Both deployment modes require a Kubernetes-based cluster:

**TESTING MODE (Mock Eventing):**
* OpenShift or Kubernetes cluster
* No special operators required
* Access to LlamaStack/LLM endpoint

**PRODUCTION MODE (Knative Eventing):**
* OpenShift cluster with:
  - OpenShift Serverless Operator
  - Streams for Apache Kafka Operator
* Access to LlamaStack/LLM endpoint

### 2.3 Access Requirements

* OpenShift cluster access (for Helm deployment)
* Container registry access (Quay.io or similar)
* LLM API endpoint and credentials
* (Optional) Slack workspace admin access for Slack integration
* (Optional) ServiceNow instance for full laptop refresh workflow

### 2.4 Knowledge Prerequisites

Helpful but not required:
* Basic understanding of Kubernetes/OpenShift
* Familiarity with REST APIs
* Understanding of AI/LLM concepts
* Experience with Python development

### 2.5 Time Estimate

* OpenShift deployment (testing mode): 45-60 minutes
* Full production deployment with Slack: 60-90 minutes
* Running evaluations: 15-30 minutes
* Customization for your use case: Varies

---

## 3. ARCHITECTURE & DEPLOYMENT MODES

### 3.1 Deployment Modes

The quickstart supports two deployment modes that share the same codebase but use different communication infrastructure. You can start with testing mode and transition to production without code changes—only configuration.

**Testing Mode (Mock Eventing)**

Testing mode uses a lightweight mock eventing service that mimics Knative broker behavior via simple HTTP routing. It's ideal for development, CI/CD pipelines, and staging environments. The mock service accepts CloudEvents and routes them to configured endpoints using the same protocols as production, but without requiring Knative operators or Kafka infrastructure. Deploy to any Kubernetes/OpenShift cluster with standard resources.

**Production Mode (Knative Eventing)**

Production mode leverages Knative Eventing with Apache Kafka for enterprise-grade event routing. It provides high availability, fault tolerance, horizontal scalability, and guaranteed delivery. Requires OpenShift Serverless Operator and Streams for Apache Kafka Operator, but delivers production-ready reliability with sophisticated retry logic and durable message queuing.

**Mode Comparison**

| Aspect | Testing Mode | Production Mode |
|--------|-------------|-----------------|
| **Infrastructure** | Basic Kubernetes/OpenShift | OpenShift + Serverless + Kafka operators |
| **Scalability** | Moderate loads | High scalability via Kafka partitioning |
| **Reliability** | Standard K8s features | Enterprise-grade with guaranteed delivery |
| **Setup** | Low complexity | Higher complexity |
| **Cost** | Lower footprint | Higher resources |

Most teams start with testing mode, then transition to production via configuration changes only—no code modifications required.

### 3.2 Request Flow

Both modes use identical services, business logic, and data models. A strategy pattern abstracts the communication mechanism, making deployment mode differences transparent to application code.

**Request Lifecycle**

1. **User initiates request** via any channel (Slack, API, CLI, email) → Integration Dispatcher receives and forwards to Request Manager

2. **Request Manager normalizes** diverse channel formats into standard internal structure, then performs validation and session management. For continuing conversations, retrieves session context from PostgreSQL (conversation history, user metadata, integration details)

3. **Agent Service processes** the request. New requests route to routing agent, which identifies user intent and hands off to appropriate specialist (e.g., laptop refresh agent). Specialist accesses knowledge bases and calls MCP server tools to complete the workflow

4. **Integration Dispatcher delivers** response back to user via their original channel, handling all channel-specific formatting

**Session Management**

The system maintains conversational context across multiple interactions regardless of channel—essential for multi-turn agent workflows. Request Manager stores session state in PostgreSQL with unique session ID, user ID, integration type, conversation history, current agent, and routing metadata.

## 4. COMPONENT OVERVIEW

The quickstart consists of reusable **core platform components** and **use-case-specific components** (demonstrated through the laptop refresh example). Core components work across any IT process without modification, while use-case components show how to customize for specific workflows.

### 4.1 Core Platform Components (Reusable Across Use Cases)

#### 4.1.1 Request Manager

**Purpose:** Central orchestrator that normalizes multi-channel requests and manages session state.

**Key Capabilities:**
- **Normalization:** Transforms diverse inputs (Slack messages, HTTP calls, CLI commands) into standardized internal format containing user message, identifier, integration type, and session context
- **Session Management:** Maintains conversational state across interactions by persisting sessions in PostgreSQL with conversation history, user metadata, and routing information

---

#### 4.1.2 Agent Service

**Purpose:** Mediates communication with agents and routing between them.

**Key Capabilities:**
- **Agent Orchestration:** Routes requests to appropriate agents (routing agent → specialist agents), managing handoffs and conversation context
- **Configuration-Driven:** Uses agents configured via YAML files in agent-service
- **Generic Design:** All domain logic comes from agent configurations—no hardcoded use-case behavior

---

#### 4.1.3 Integration Dispatcher

**Purpose:** Multi-channel delivery hub that sends/receives messages through various communication channels.

**Key Capabilities:**
- **Channel Handlers:** Registry of handlers for Slack, Email, SMS, webhooks—each handles channel-specific protocols and formatting
- **Bidirectional Communication:** Implements webhook endpoints (e.g., Slack events), verifies signatures, extracts messages, forwards to Request Manager
- **Extensible Architecture:** Add custom channels (Teams, mobile apps) by implementing new handlers without core logic changes

---

#### 4.1.4 Agent Service

**Purpose:** AI agent processing service that handles agent registration, knowledge base management, and LangGraph state machine execution.

**Key Capabilities:**
- **Agent Registration:** Reads YAML files from `agent-service/config/agents/`, registers agents with their instructions, tools, and knowledge bases
- **Knowledge Base Creation:** Processes text documents, creates embeddings, builds vector databases, registers for RAG queries
- **Safety Shields:** Content moderation for input/output using Llama Guard 3 or compatible models, with configurable category filtering for false positive handling (see [Safety Shields Guide](guides/SAFETY_SHIELDS_GUIDE.md))

---

#### 4.1.5 Mock Eventing Service

**Purpose:** Lightweight service that mimics Knative broker behavior for testing event-driven flows without complex infrastructure.

**Key Capabilities:**
- **Event Routing:** Accepts CloudEvents via HTTP, applies routing rules, forwards to destination services—identical protocols to production
- **In-Memory Configuration:** Routes event types (`agent.request` → Agent Service, `integration.delivery` → Integration Dispatcher)
- **Fast Iteration:** Instant startup, minimal resources, easy debugging—ideal for CI/CD pipelines and local development

---

#### 4.1.6 Shared Libraries

**Purpose:** Foundational libraries ensuring consistency across all services through centralized data models and client implementations.

**shared-models:**
- **Database Schema:** SQLAlchemy models for database tables—single source of truth across all services
- **Pydantic Schemas:** Request/response validation with type safety and automatic serialization
- **Alembic Migrations:** Schema evolution management without manual SQL scripts

**shared-clients:**
- **HTTP Clients:** Standardized implementations for inter-service communication (AgentServiceClient, IntegrationDispatcherClient)

---

#### 4.1.7 Communication Integrations

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

---

#### 4.1.8 Observability

**Purpose:** Monitor system behavior, track performance, and troubleshoot production issues.

**Key Capabilities:**
- **Distributed Tracing**: OpenTelemetry + Jaeger for request lifecycle visibility across all services
- **Performance Monitoring**: Track agent response latency, tool call timing, knowledge base retrieval performance
- **Error Tracking**: Debug failed integrations, conversation routing issues, ticket creation errors
- **Business KPIs**: Measure completion rates, user satisfaction, end-to-end request timing

**Integration:** Works with OpenShift observability stack—unified monitoring across platform components and existing infrastructure

**Reusability:** Infrastructure works for any use case without changes—add custom metrics for specific KPIs (PIA completion, RFP quality, etc.)

---

#### 4.1.9 Evaluation Framework

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

---

### 4.2 Laptop Refresh Specific Components

These components build on the common components to implement the laptop refresh process. Apply the same patterns for your own use cases (PIA, RFP, etc.).

#### 4.2.1 MCP Servers

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

#### 4.2.2 Knowledge Bases

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

**Knowledge Base Updates:**

This quickstart uses an implementation where knowledge base documents are static text files loaded and ingested during agent service initialization. This approach allows you to get started quickly without complex infrastructure and is used as knowledge base creation and ongoing management is not the focus of this quickstart.

However, production deployments typically require a more sophisticated approach for updating knowledge bases as policies and documentation change. For production use cases, consider implementing a dedicated ingestion pipeline that can:
- Process updates from multiple source systems (SharePoint, Confluence, document management systems)
- Handle incremental updates without full redeployment
- Support various document formats (PDF, Word, HTML, etc.)
- Provide automated document processing and chunking
- Enable continuous synchronization of knowledge bases

For a complete ingestion pipeline architecture and implementation guidance, see the **[Ingestion Pipeline](https://github.com/rh-ai-quickstart/ai-architecture-charts/tree/main/ingestion-pipeline)** in the AI Architecture Charts repository. This architecture provides a production-ready approach to knowledge base management that can scale with your organization's needs. This quickstart could easily be adapted to use pre-existing knowledge bases managed by the ingestion pipeline by simply removing the knowledge base registration step from the init-job (`helm/templates/init-job.yaml`) and updating agent configurations to reference the existing vector store IDs created by your ingestion pipeline. 

---

#### 4.2.3 Agents

**Purpose:** YAML configurations defining agent behavior, system instructions, accessible tools, and knowledge bases—registered with LlamaStack by Agent Service.

**Laptop Refresh Agent Architecture (Routing Pattern):**

**Routing Agent:**
- **Role:** Front door—greets users, identifies intent, routes to appropriate specialist
- **Tools/Knowledge:** None—purely conversation and routing logic
- **Instructions:** Recognizes request types ("I need a new laptop" → laptop refresh specialist, "privacy assessment" → PIA specialist)
- **Extensibility:** Add specialists, update routing instructions—becomes conversational switchboard

**Laptop Refresh Specialist Agent:**
- **Role:** Domain expert guiding laptop refresh process
- **Instructions:** Process flow (check eligibility, present options, create ticket), compliance requirements, interaction style
- **Tools:** ServiceNow tools (laptop information, ticket creation)
- **Knowledge Base:** `laptop-refresh` knowledge base for policy questions
- **Capabilities:** Queries knowledge base for policies, calls tools to check eligibility/retrieve options/create tickets

---

#### 4.2.4 Evaluations

**Purpose:** Laptop refresh-specific conversation flows and metrics that validate the agent's ability to handle laptop refresh requests correctly.

**Predefined Conversation Flows:**
- **Success flow**: Complete laptop refresh request from greeting through ticket creation
- **Location**: `evaluations/conversations_config/conversations/`

**Custom Evaluation Metrics** (in `get_deepeval_metrics.py`):
- **Information Gathering**: Collects laptop info and employee ID
- **Policy Compliance**: Correctly applies 3-year refresh policy with accurate eligibility determinations
- **Option Presentation**: Presents appropriate laptop options based on user location
- **Process Completion**: Completes flow (eligibility → options → selection → ticket creation)
- **User Experience**: Maintains helpfulness, professionalism, clarity
- **Flow Termination**: Ends with ticket number or DONEDONEDONE
- **Ticket Number Validation**: ServiceNow format (REQ prefix)
- **Correct Eligibility Validation**: Accurate 3-year policy timeframe
- **No Errors Reported**: No system problems
- **Correct Laptop Options for Location**: All location-specific models presented
- **Confirmation Before Ticket Creation**: Agent asks user confirmation (no-employee-id flow)
- **Employee ID Requested**: Agent requests employee ID (standard flow)

---

## 5. HANDS-ON QUICKSTART

This section walks you through deploying and testing the laptop refresh agent on OpenShift.

### 5.1 Deploy to OpenShift

#### Step 1: Choose Your Deployment Mode

For first deployment, we recommend **Testing Mode (Mock Eventing)**:
- No Knative operators required
- Tests event-driven patterns
- Simpler than production infrastructure

#### Step 2: Set Required Environment Variables

```bash
# Set your namespace
export NAMESPACE=your-namespace

# Set LLM configuration
export LLM=llama-3-2-1b-instruct
export LLM_API_TOKEN=your-api-token
export LLM_URL=https://your-llm-endpoint

# Set integration secrets (optional for initial testing)
export SLACK_SIGNING_SECRET=your-slack-secret  # Optional
export SNOW_API_KEY=your-servicenow-key       # Optional

# Set container registry (if using custom builds)
export REGISTRY=quay.io/your-org
```

#### Step 3: Build Container Images (Optional)

If using pre-built images, skip this step.

```bash
# Build all images
make build-all-images

# Push to registry
make push-all-images
```

**Expected outcome:** All images built and pushed to registry

#### Step 4: Deploy with Helm

```bash
# Login to OpenShift
oc login --server=https://your-cluster:6443

# Create namespace if needed
oc new-project $NAMESPACE

# Deploy in testing mode (Mock Eventing)
make helm-install-test NAMESPACE=$NAMESPACE
```

**Expected outcome:**
- ✓ Helm chart deployed successfully
- ✓ All pods running
- ✓ Routes created

#### Step 5: Verify Deployment

```bash
# Check deployment status
make helm-status NAMESPACE=$NAMESPACE

# Check pods
oc get pods -n $NAMESPACE

# Check routes
oc get routes -n $NAMESPACE
```

**Expected outcome:**
- All pods in Running state
- Routes accessible
- Agent service initialization completed successfully

#### Step 6: Test the Deployment

```bash
# Get the request manager route
export REQUEST_MANAGER_URL=$(oc get route request-manager -n $NAMESPACE -o jsonpath='{.spec.host}')

# Send test request
curl -X POST https://$REQUEST_MANAGER_URL/api/v1/requests \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, I need help with my laptop",
    "user_id": "test-user",
    "integration_type": "cli"
  }'
```

**Expected outcome:** Agent greeting response

**You should now be able to:**
- ✓ Deploy the system to OpenShift
- ✓ Access agents via public routes
- ✓ Monitor pods and services
- ✓ Troubleshoot deployment issues

---

### 5.2 Interact with the CLI

Now that the system is deployed, let's interact with the agent through the CLI to test a complete laptop refresh workflow.

#### Step 1: Start Interactive Chat Session

Use the CLI chat script to start an interactive conversation with the agent:

```bash
# Get the request manager pod
export REQUEST_MANAGER_POD=$(oc get pod -n $NAMESPACE -l app=self-service-agent-request-manager -o jsonpath='{.items[0].metadata.name}')

# Start interactive chat session
oc exec -it $REQUEST_MANAGER_POD -n $NAMESPACE -- \
  python test/chat-responses-request-mgr.py \
  --user-id alice.johnson@company.com
```

**Expected outcome:**
- Chat client starts in interactive mode
- Agent sends initial greeting
- You see a prompt where you can type messages

#### Step 2: Complete Laptop Refresh Workflow

Follow this conversation flow to test the complete laptop refresh process:

**You:** `I need help with my laptop refresh`

**Expected:** Agent greets you and retrieves your current laptop information

**You:** `I would like to see available laptop options`

**Expected:**
- Agent checks your eligibility based on 3-year policy
- Agent presents available laptop options for your region (NA, EMEA, APAC, or LATAM)
- You see 4 laptop options with specifications and pricing

**You:** `I would like option 1, the Apple MacBook Air M3`

**Expected:** Agent confirms your selection and asks for approval to create ServiceNow ticket

**You:** `Yes, please create the ticket`

**Expected:**
- ServiceNow ticket created
- Ticket number provided (format: REQ followed by digits)
- Confirmation message with next steps

**You:** `DONEDONEDONE`

**Expected:** Chat session ends

#### Step 3: Test Different User Scenarios

Test with different employee IDs to see varied scenarios:

```bash
# Test with different user (EMEA region)
oc exec -it $REQUEST_MANAGER_POD -n $NAMESPACE -- \
  python test/chat-responses-request-mgr.py \
  --user-id john.doe@company.com

# Test with user who may not be eligible
oc exec -it $REQUEST_MANAGER_POD -n $NAMESPACE -- \
  python test/chat-responses-request-mgr.py \
  --user-id maria.garcia@company.com
```

**Expected outcome:**
- Different laptop options based on region
- Different eligibility results based on laptop age
- Consistent agent behavior across scenarios

**You should now be able to:**
- ✓ Interact with agents via CLI using interactive chat
- ✓ Complete full laptop refresh workflow
- ✓ Test conversation flows with different users
- ✓ Verify agent behavior and responses
- ✓ Test eligibility checking and region-specific options

---

### 5.3 Integration with Slack (Optional)

Slack integration enables real-world testing with actual users in your workspace.

#### Step 1: Set Up Slack App

See [`SLACK_SETUP.md`](guides/SLACK_SETUP.md) for detailed instructions.

**Summary:**
1. Create Slack app at [api.slack.com/apps](https://api.slack.com/apps)
2. Configure OAuth scopes (chat:write, channels:history, etc.)
3. Enable Event Subscriptions
4. Set Request URL to your Integration Dispatcher route
5. Install app to workspace
6. Copy signing secret and bot token

#### Step 2: Update Deployment with Slack Credentials

```bash
# Set Slack credentials
export SLACK_SIGNING_SECRET=your-signing-secret
export SLACK_BOT_TOKEN=your-bot-token

# Upgrade Helm deployment
make helm-upgrade NAMESPACE=$NAMESPACE
```

#### Step 3: Verify Slack Integration

Check the Integration Dispatcher health endpoint to confirm Slack integration is active:

```bash
# Check integration health
kubectl exec deployment/self-service-agent-integration-dispatcher -n $NAMESPACE -- \
  curl -s http://localhost:8080/health/detailed | jq '.integrations_available'

# Look for "SLACK" in the integrations_available array
```

#### Step 4: Test Slack Interaction

In your Slack workspace:

1. Invite bot to a channel: `/invite @your-bot`
2. Send message: `@your-bot I need a new laptop`
3. Agent responds with greeting and laptop information
4. Agent presents available laptop options
5. Select a laptop: `I'd like option 1`
6. Agent creates ServiceNow ticket and provides ticket number

**Expected outcome:**
- ✓ Bot responds in Slack thread
- ✓ Conversation maintains context across multiple messages
- ✓ Agent retrieves employee laptop info automatically (using Slack email)
- ✓ Agent shows laptop options for employee's region
- ✓ Ticket created with confirmation number

**You should now be able to:**
- ✓ Interact with agents via Slack
- ✓ Test real-world user experience
- ✓ Demonstrate system to stakeholders
- ✓ Gather user feedback from actual employees

---

### 5.4 Integration with Real ServiceNow (Optional)

By default, the system uses mock ServiceNow data. To integrate with your actual ServiceNow instance see the following docs for full details. The sections which follow walk you through the streamlined processes for setting up and using a ServiceNow instance.
- [ServiceNow PDI Bootstrap - Automated Setup](guides/SERVICE_NOW_BOOTSTRAP_AUTOMATED.md) - for a guide to automated ServiceNow Bootstrap (recommended)
- [ServiceNow PDI Bootstrap - Manual Setup](guides/SERVICE_NOW_BOOTSTRAP_MANUAL.md) - for a guide to manual ServiceNow Bootstrap

#### Step 1: Configure ServiceNow Credentials

```bash
# Set ServiceNow configuration
export SERVICENOW_INSTANCE_URL=https://your-instance.service-now.com
export SERVICENOW_API_KEY=your-servicenow-api-key
export SERVICENOW_LAPTOP_REFRESH_ID=your-servicenow-laptop-refresh-id

# Upgrade Helm deployment
make helm-upgrade NAMESPACE=$NAMESPACE
```

#### Step 2: Verify ServiceNow Connection

Check the ServiceNow MCP server logs to confirm connection:

```bash
# View MCP server logs
oc logs deployment/mcp-snow -n $NAMESPACE

# Look for successful ServiceNow API calls
# Example: "ServiceNow API request completed - employee ID: alice.johnson@company.com"
```

#### Step 3: Test with Real ServiceNow

Use the CLI chat client to initiate a laptop refresh request with your real ServiceNow account:

```bash
# Get the request manager pod
export REQUEST_MANAGER_POD=$(oc get pod -n $NAMESPACE -l app=request-manager -o jsonpath='{.items[0].metadata.name}')

# Start chat session with your email
oc exec -it $REQUEST_MANAGER_POD -n $NAMESPACE -- \
  python test/chat-responses-request-mgr.py \
  --user-id your-email@company.com
```

Then complete the laptop refresh workflow:

**You:** `I need a laptop refresh`

**You:** `I would like to see available laptop options`

**You:** `I would like option [number]`

**You:** `Yes, please create the ticket`

**Expected outcome:**
- Agent retrieves your actual laptop data from ServiceNow
- Agent creates real ServiceNow ticket when you confirm
- Ticket appears in your ServiceNow instance
- You receive ServiceNow notifications via email

#### Step 4: Verify in ServiceNow

Log into your ServiceNow instance and verify:
- Ticket was created in the correct category
- Ticket contains accurate information (employee, laptop choice, justification)
- Ticket is assigned to appropriate group
- Ticket follows your ServiceNow workflows

**You should now be able to:**
- ✓ Connect to production ServiceNow instance
- ✓ Create real tickets from agent conversations
- ✓ Test end-to-end integration with backend systems
- ✓ Validate data accuracy in ServiceNow

---

### 5.5 Integration with Email (Optional)

Email integration enables two-way communication with the AI agent through email, allowing users to interact with the system via their email client.

#### Step 1: Set Up Email Configuration

See [`EMAIL_SETUP.md`](guides/EMAIL_SETUP.md) for detailed instructions.

**Summary:**
1. Choose an email provider (Gmail, Outlook, or custom SMTP/IMAP)
2. Get SMTP credentials for sending emails
3. Get IMAP credentials for receiving emails (optional, for polling)
4. Configure email account settings (enable IMAP if needed)

#### Step 2: Update Deployment with Email Credentials

```bash
# Set email configuration
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export IMAP_HOST=imap.gmail.com
export IMAP_PORT=993

# Upgrade Helm deployment with email configuration
make helm-upgrade NAMESPACE=$NAMESPACE \
  EXTRA_HELM_ARGS="\
    --set-string security.email.smtpHost=$SMTP_HOST \
    --set-string security.email.smtpPort=$SMTP_PORT \
    --set-string security.email.smtpUsername=$SMTP_USERNAME \
    --set-string security.email.smtpPassword=$SMTP_PASSWORD \
    --set-string security.email.smtpUseTls=true \
    --set-string security.email.fromEmail=$SMTP_USERNAME \
    --set-string security.email.fromName='Self-Service Agent' \
    --set-string security.email.imapHost=$IMAP_HOST \
    --set-string security.email.imapPort=$IMAP_PORT \
    --set-string security.email.imapUseSsl=true \
    --set-string security.email.imapMailbox=INBOX \
    --set-string security.email.imapPollInterval=60 \
    --set-string security.email.imapLeaseDuration=120"
```

#### Step 3: Verify Email Integration

Check the Integration Dispatcher health endpoint to confirm email integration is active:

```bash
# Check integration health and email capabilities
kubectl exec deployment/self-service-agent-integration-dispatcher -n $NAMESPACE -- \
  curl -s http://localhost:8080/health/detailed | jq '{integrations_available, email_capabilities: .services.email_capabilities}'

# Look for:
# - "EMAIL" in the integrations_available array
# - email_capabilities showing sending: true and/or receiving: true
```

#### Step 4: Test Email Interaction

Send an email to the configured email address (`FROM_EMAIL` or `SMTP_USERNAME`):

1. Send email from your email client to the configured address
2. Subject: "I need help with my laptop refresh"
3. Body: "Hi, I'd like to start a laptop refresh request"

**Expected outcome:**
- ✓ Email received and processed by Integration Dispatcher
- ✓ Agent responds via email with greeting and laptop information
- ✓ Conversation maintains context across email replies
- ✓ Agent presents laptop options for your region
- ✓ Ticket created with confirmation sent via email

#### Step 5: Test Email Threading

Reply to the agent's email to test conversation threading:

1. Reply to the agent's email (maintains In-Reply-To header)
2. Continue the conversation: "I'd like to see available laptop options"
3. Agent responds in the same email thread

**Expected outcome:**
- ✓ Email threading works correctly
- ✓ Conversation context maintained across multiple emails
- ✓ Agent remembers previous messages in the thread

**You should now be able to:**
- ✓ Interact with agents via email
- ✓ Receive email notifications and responses
- ✓ Maintain conversation context through email threads
- ✓ Test email integration end-to-end

---

### 5.6 Setting up Safety Shields (Optional)

Safety shields provide content moderation for AI agent interactions, validating user input and agent responses against safety policies using Llama Guard 3 or compatible models.

#### When to Enable Safety Shields

Consider enabling safety shields for:
- **Customer-facing agents**: Public or external user interactions
- **Compliance requirements**: Organizations with strict content policies
- **High-risk applications**: Agents handling sensitive topics

**Note:** Safety shields come with the possibility of false positives. False positives that result in
blocking input or output messages can mess up the IT process flow resulting in process failures.
Common safety models like llama-guard that are desired for interaction with external users may not
be suited for the content of common IT processes. We have disabled a number of the categories
for which we regularly saw false positives.

For development and testing, shields can be disabled for faster iteration.

#### Step 1: Deploy with Safety Shield Configuration

Safety shields require an OpenAI-compatible moderation API endpoint:

```bash
# Deploy with safety shields enabled
make helm-install-test NAMESPACE=$NAMESPACE \
  LLM=llama-3-2-1b-instruct \
  SAFETY=meta-llama/Llama-Guard-3-8B \
  SAFETY_URL=https://api.example.com/v1
```

**Note**:
- Replace `https://api.example.com/v1` with your actual moderation API endpoint
- The endpoint must support the OpenAI-compatible `/v1/moderations` API
- For in-cluster deployments, you can use a vLLM instance (e.g., `http://vllm-service:8000/v1`)
- If `SAFETY` and `SAFETY_URL` are not set, shields will be automatically disabled even if configured in agent YAML files

#### Step 2: Configure Agent-Level Shields

Edit your agent configuration file (e.g., `agent-service/config/agents/laptop-refresh-agent.yaml`):

```yaml
name: "laptop-refresh"
description: "An agent that can help with laptop refresh requests."

# Input shields - validate user input before processing
input_shields: ["meta-llama/Llama-Guard-3-8B"]

# Output shields - validate agent responses before delivery
output_shields: []
```

**Shield Configuration Options:**
- **`input_shields`**: List of models to validate user messages (recommended)
- **`output_shields`**: List of models to validate agent responses (optional, impacts performance)
- **`ignored_input_shield_categories`**: Categories to allow in user input (handles false positives)
- **`ignored_output_shield_categories`**: Categories to allow in agent responses

#### Step 3: Test Safety Shields

After deploying with shields enabled, test that they're working:

```bash
# Check agent service logs for shield initialization
oc logs deployment/self-service-agent-agent-service -n $NAMESPACE | grep -i shield

# Expected output:
# INFO: Input shields configured: ['meta-llama/Llama-Guard-3-8B']
# INFO: Ignored input categories: {'Code Interpreter Abuse', 'Privacy', ...}
```

#### Common Shield Categories

Llama Guard 3 checks for these categories:
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

For comprehensive safety shields documentation, see the [Safety Shields Guide](guides/SAFETY_SHIELDS_GUIDE.md).

**You should now be able to:**
- ✓ Configure safety shields for content moderation
- ✓ Customize shield behavior per agent
- ✓ Handle false positives with ignored categories
- ✓ Monitor and troubleshoot shield operations
- ✓ Balance safety and usability for your use case

---

### 5.7 Run Evaluations

The evaluation framework validates agent behavior against business requirements and quality metrics.

#### Step 1: Configure Evaluation Environment

```bash
cd evaluations/

# Set LLM endpoint for evaluation (can use different model than agent)
export LLM_API_TOKEN=your-evaluation-llm-token
export LLM_URL=https://your-evaluation-llm-endpoint
export LLM_ID=your-model-id

# Install evaluation dependencies (using pip for evaluation framework)
# Note: The evaluation framework uses pip; the main services use uv
pip install -e .
```

#### Step 2: Run Predefined Conversation Flows

Execute the predefined conversation flows against your deployed agent:

```bash
# Run predefined conversations
python run_conversations.py
```

**Expected outcome:**
- ✓ Conversations executed against deployed agent
- ✓ Results saved to `results/conversation_results/`
- ✓ Files like `success-flow.json`, `edge-case-ineligible.json`

Review a conversation result:
```bash
cat results/conversation_results/success-flow.json
```

You should see the complete conversation with agent responses at each turn.

#### Step 3: Generate Synthetic Test Conversations

Create additional test scenarios using the conversation generator:

```bash
# Generate 5 synthetic conversations
python generator.py 5 --max-turns 20
```

**Expected outcome:**
- ✓ 5 generated conversations saved to `results/conversation_results/`
- ✓ Diverse scenarios with varied user inputs
- ✓ Different edge cases automatically explored

#### Step 4: Evaluate All Conversations

Run the evaluation metrics against all conversation results:

```bash
# Evaluate with business metrics
python deep_eval.py
```

**Expected outcome:**
- ✓ Each conversation evaluated against 15 metrics
- ✓ Results saved to `results/deep_eval_results/`
- ✓ Aggregate metrics in `deepeval_all_results.json`

#### Step 5: Review Evaluation Results

```bash
# View evaluation summary
cat results/deep_eval_results/deepeval_all_results.json
```

**Key metrics to review:**
- **Information Gathering**: Did agent collect required data? (Target: > 0.8)
- **Policy Compliance**: Did agent follow 3-year refresh policy correctly? (Target: > 0.9)
- **Option Presentation**: Were laptop options shown correctly? (Target: > 0.8)
- **Process Completion**: Were tickets created successfully? (Target: > 0.85)
- **User Experience**: Was agent helpful and clear? (Target: > 0.8)
- **Correct Laptop Options for Location**: All region-specific models presented? (Target: 1.0)
- **Ticket Number Validation**: ServiceNow format (REQ prefix)? (Target: 1.0)

#### Step 6: Run Complete Evaluation Pipeline

Run the full pipeline in one command:

```bash
# Complete pipeline: predefined + generated + evaluation
python evaluate.py --num-conversations 5
```

**Expected outcome:**
- ✓ Predefined flows executed
- ✓ 5 synthetic conversations generated
- ✓ All conversations evaluated
- ✓ Comprehensive results report with aggregate metrics
- ✓ Identification of failing conversations for debugging

**You should now be able to:**
- ✓ Execute evaluation pipelines
- ✓ Generate synthetic test conversations
- ✓ Evaluate agent performance with business metrics
- ✓ Identify areas for improvement
- ✓ Validate agent behavior before production deployment
- ✓ Catch regressions when updating prompts or models

---

### 5.8 Follow the Flow with Observability

(Documentation TBD)

---

## 6. PERFORMANCE & SCALING

The Self-Service Agent quickstart is designed for scalability using standard Kubernetes and cloud-native patterns. All core components can be scaled using familiar Kubernetes techniques—horizontal pod autoscaling, replica sets, and resource limits—without requiring custom scaling logic or architectural changes.

**Component Scaling:** The quickstart's services follow standard cloud-native design principles. Most services (mock-eventing, agent-service, integration-dispatcher) can scale both vertically (multiple uvicorn workers per pod) and horizontally (multiple pod replicas) to handle increased load. MCP servers use the FastMCP framework with Server-Sent Events (SSE) transport, which requires single-worker deployments but scales effectively through horizontal replication.

**Infrastructure Scaling:** For supporting infrastructure components, apply industry-standard scaling techniques. PostgreSQL databases can leverage connection pooling, read replicas, and vertical scaling following standard PostgreSQL best practices. When using production mode with Knative Eventing, Apache Kafka benefits from standard Kafka scaling strategies including partitioning, consumer groups, and multi-broker clusters. These are well-documented patterns with extensive ecosystem support.

**Performance Optimization:** Analysis of some evaluation runs shows that 99.7% of request processing time is spent in Llama Stack inference, with the request-manager and event delivery adding only negligible overhead (~12ms total). This means performance optimization efforts should focus primarily on LLM inference scaling—using GPU acceleration, deploying multiple Llama Stack replicas, and selecting appropriately-sized models. The quickstart's architecture ensures that scaling Llama Stack directly translates to end-to-end performance improvements without infrastructure bottlenecks.

For comprehensive scaling guidance, detailed performance characteristics, component-by-component scaling analysis, configuration examples for different deployment sizes, and links to Red Hat and Llama Stack documentation, see the **[Performance and Scaling Guide](guides/PERFORMANCE_SCALING_GUIDE.md)**.

---

## 7. GOING DEEPER: COMPONENT DOCUMENTATION

Now that you have the system running, dive deeper into each component.

### 7.1 Core Platform

**Request Manager**
- Full documentation: `request-manager/README.md`
- Topics: Session management, request normalization, routing logic

**Agent Service**
- Full documentation: `agent-service/README.md` (TBD)
- Topics: LlamaStack integration, tool calling, streaming responses

**Integration Dispatcher**
- Full documentation: `integration-dispatcher/README.md` (TBD)
- Topics: Multi-channel delivery, integration handlers, user overrides

**Shared Libraries**
- Full documentation: [`shared-clients/README.md`](shared-clients/README.md)
- `shared-models`: Database models, schemas, migrations
- `shared-clients`: HTTP client implementations

---

### 7.2 Agent Configuration

**Agent Service**
- Topics: Agent registration, knowledge base creation, LangGraph state machine

**Agent Configurations**
- Directory: `agent-service/config/agents/`
- Examples: `routing-agent.yaml`, `laptop-refresh.yaml`

**Prompt Configuration**
- Full documentation: [`docs/PROMPT_CONFIGURATION_GUIDE.md`](docs/PROMPT_CONFIGURATION_GUIDE.md)
- Topics: System prompts, few-shot examples, prompt engineering

**Knowledge Bases**
- Directory: `agent-service/config/knowledge_bases/`
- Structure: One directory per knowledge base
- Format: `.txt` files automatically indexed

**MCP Servers**
- Full documentation: [`mcp-servers/snow/README.md`](mcp-servers/snow/README.md)
- Topics: ServiceNow integration, tool implementation

---

### 7.3 External Integrations

**Slack Setup**
- Full documentation: [`guides/SLACK_SETUP.md`](guides/SLACK_SETUP.md)
- Topics: App creation, OAuth, event subscriptions

**Email Setup**
- Full documentation: [`guides/EMAIL_SETUP.md`](guides/EMAIL_SETUP.md)
- Topics: SMTP configuration, IMAP polling, email threading

**ServiceNow Integration**
- (Documentation TBD)

---

### 7.4 Quality & Operations

**Evaluation Framework**
- Full documentation: [`evaluations/README.md`](evaluations/README.md)
- Topics: Conversation flows, metrics, generation, pipeline

**Observability**
- Full documentation: `tracing-config/README.md` (TBD)
- Topics: OpenTelemetry, Jaeger, distributed tracing

---

## 8. CUSTOMIZING FOR YOUR USE CASE

The laptop refresh example demonstrates all components. This section guides you in adapting the quickstart for your own IT process.

### 8.1 Planning Your Use Case

#### Step 1: Define Your IT Process

Questions to answer:
- What IT process are you automating? (PIA, RFP, access requests, etc.)
- What are the steps a user goes through?
- What information does the agent need to collect?
- What systems does the agent need to interact with?
- What policies or rules govern the process?
- How do you measure success?

**Example: Privacy Impact Assessment (PIA)**

Process steps:
1. User requests PIA assessment
2. Agent asks about project details (name, scope, data types)
3. Agent asks privacy-specific questions
4. Agent evaluates risk level based on responses
5. Agent generates PIA document
6. Agent submits to compliance team

#### Step 2: Identify Required Integrations

For each external system, determine:
- What data do you need to read?
- What actions do you need to perform?
- Does an API exist?
- What authentication is required?

**Example: PIA Assessment**
- Compliance system API: Submit PIA documents
- HR system: Get employee and project info
- Document storage: Save generated PIAs
- Email: Notify compliance team

#### Step 3: Map Knowledge Requirements

What knowledge does the agent need?
- Policy documents
- Process guidelines
- Templates
- FAQs
- Legal/compliance requirements

**Example: PIA Assessment**
- Privacy laws and regulations
- PIA question templates
- Risk assessment criteria
- Data classification guidelines
- Example PIAs for reference

#### Step 4: Define Success Metrics

How will you evaluate the agent?
- Process completion rate
- Information accuracy
- Policy compliance
- User satisfaction
- Time to completion

**Example: PIA Assessment**
- Did agent ask all required privacy questions?
- Was risk level assessed correctly?
- Did generated PIA meet compliance standards?
- Was submission successful?

## 9. NEXT STEPS AND ADDITIONAL RESOURCES

### 9.1 What You've Accomplished

By completing this quickstart, you have:

- ✓ Deployed a fully functional AI agent system on OpenShift
- ✓ Understood the core platform architecture and components
- ✓ Tested the laptop refresh agent through multiple channels
- ✓ Run evaluations to validate agent behavior
- ✓ Learned how to customize the system for your own use cases

### 9.2 Recommended Next Steps

**For Development Teams:**
1. Review the [Contributing Guide](docs/CONTRIBUTING.md) for development setup and workflow
2. Explore the component documentation in Section 7 for deeper technical details
3. Review the evaluation framework to understand quality metrics
4. Experiment with customizing the laptop refresh agent prompts
5. Set up observability and monitoring for your deployment

**For Organizations Planning Production Deployment:**
1. Plan your transition from testing mode to production mode (Knative Eventing)
2. Identify your first use case for customization
3. Establish evaluation criteria and quality metrics for your use case
4. Plan integration with your existing IT service management systems

**For Customizing to Your Use Case:**
1. Follow the planning guide in Section 8.1
2. Review the laptop refresh implementation as a reference (Section 4.2)
3. Start with agent configuration and knowledge base development
4. Build MCP servers for your external systems
5. Develop use-case-specific evaluation metrics

---

**Thank you for using the Self-Service Agent Quickstart!** We hope this guide helps you successfully deploy AI-driven IT process automation in your organization.

## Tracing

To enable tracing, it is possible to specify a remote OpenTelemetry collector,
with the `OTEL_EXPORTER_OTLP_ENDPOINT` environement variable.

```bash
make helm-install-test LLM=llama-3-3-70b-instruct-w8a8 LLM_ID=llama-3-3-70b-instruct-w8a8 LLM_URL=$YOUR_LLM_URL LLM_API_TOKEN=$YOUR_LLM_API_TOKEN OTEL_EXPORTER_OTLP_ENDPOINT="http://jaeger-collector.obs.svc.cluster.local:4318"
```
