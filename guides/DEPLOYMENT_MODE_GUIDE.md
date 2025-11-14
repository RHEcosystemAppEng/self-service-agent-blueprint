# Deployment Mode Guide

This guide explains the two deployment modes available for the Self-Service Agent system and helps you choose the right one for your needs.

## Overview

The quickstart supports two deployment modes that share the same codebase but use different communication infrastructure. You can start with testing mode and transition to production without code changes—only configuration.

## Deployment Modes

### Testing Mode (Mock Eventing)

Testing mode uses a lightweight mock eventing service that mimics Knative broker behavior via simple HTTP routing. It's ideal for development, CI/CD pipelines, and staging environments. The mock service accepts CloudEvents and routes them to configured endpoints using the same protocols as production, but without requiring Knative operators or Kafka infrastructure. Deploy to any Kubernetes/OpenShift cluster with standard resources.

**Best for:**
- Development and testing environments
- CI/CD pipelines
- Staging environments
- Quick setup and iteration
- Environments without Knative infrastructure

**Key characteristics:**
- Low complexity setup
- Minimal resource requirements
- Identical event-driven patterns as production
- No Knative operators required
- Fast debugging and troubleshooting

### Production Mode (Knative Eventing)

Production mode leverages Knative Eventing with Apache Kafka for enterprise-grade event routing. It provides high availability, fault tolerance, horizontal scalability, and guaranteed delivery. Requires OpenShift Serverless Operator and Streams for Apache Kafka Operator, but delivers production-ready reliability with sophisticated retry logic and durable message queuing.

**Best for:**
- Production deployments
- High-availability requirements
- Large-scale deployments
- Enterprise reliability needs
- Multi-tenant environments

**Key characteristics:**
- Enterprise-grade reliability
- High availability and fault tolerance
- Horizontal scalability via Kafka
- Guaranteed message delivery
- Sophisticated retry logic

## Mode Comparison

| Aspect | Testing Mode | Production Mode |
|--------|-------------|-----------------|
| **Infrastructure** | Basic Kubernetes/OpenShift | OpenShift + Serverless + Kafka operators |
| **Scalability** | Moderate loads | High scalability via Kafka partitioning |
| **Reliability** | Standard K8s features | Enterprise-grade with guaranteed delivery |
| **Setup** | Low complexity | Higher complexity |
| **Cost** | Lower footprint | Higher resources |

Most teams start with testing mode, then transition to production via configuration changes only—no code modifications required.

## Request Flow

Both modes use identical services, business logic, and data models. A strategy pattern abstracts the communication mechanism, making deployment mode differences transparent to application code.

### Request Lifecycle

1. **User initiates request** via any channel (Slack, API, CLI, email) → Integration Dispatcher receives and forwards to Request Manager

2. **Request Manager normalizes** diverse channel formats into standard internal structure, then performs validation and session management. For continuing conversations, retrieves session context from PostgreSQL (conversation history, user metadata, integration details)

3. **Agent Service processes** the request. New requests route to routing agent, which identifies user intent and hands off to appropriate specialist (e.g., laptop refresh agent). Specialist accesses knowledge bases and calls MCP server tools to complete the workflow

4. **Integration Dispatcher delivers** response back to user via their original channel, handling all channel-specific formatting

### Session Management

The system maintains conversational context across multiple interactions regardless of channel—essential for multi-turn agent workflows. Request Manager stores session state in PostgreSQL with unique session ID, user ID, integration type, conversation history, current agent, and routing metadata.

## Choosing the Right Mode

### Start with Testing Mode if:
- You're evaluating the system
- You're developing new features
- You're running in CI/CD
- You want quick setup and iteration
- You don't need enterprise-grade reliability yet

### Move to Production Mode when:
- You're ready for production deployment
- You need high availability
- You require guaranteed message delivery
- You're scaling to handle significant load
- You have enterprise reliability requirements

## Transitioning from Testing to Production

The beauty of this architecture is that transitioning from testing mode to production mode requires **only configuration changes**—no code modifications needed.

### Transition Steps:

1. **Install required operators** (if not already present):
   - OpenShift Serverless Operator
   - Streams for Apache Kafka Operator

2. **Deploy with production configuration**:
   ```bash
   make helm-install-prod NAMESPACE=your-namespace
   ```

3. **Verify deployment**:
   ```bash
   make helm-status NAMESPACE=your-namespace
   ```

The same application code, container images, and business logic work in both modes.

## Technical Details

For detailed flow diagrams and technical architecture details, see [Architecture Diagrams](../docs/ARCHITECTURE_DIAGRAMS.md).

For deployment instructions, see:
- [Section 3: Hands-On Quickstart](../README.md#3-hands-on-quickstart) in the main README
- [Performance & Scaling Guide](PERFORMANCE_SCALING_GUIDE.md) for scaling considerations
