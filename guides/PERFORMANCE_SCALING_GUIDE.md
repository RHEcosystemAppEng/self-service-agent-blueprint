# Performance and Scaling Guide

## Overview

The Self-Service Agent quickstart is designed for scalability using standard Kubernetes and cloud-native patterns. This guide covers performance characteristics, scaling strategies, and optimization approaches for production deployments.

## Key Performance Characteristics

### Request Processing Performance

Analysis of 437 requests during an evaluation with a shared hosted llama 3 70b model showed:

**Average Total Time: 4.59 seconds**
- **Fast (< 2s):** 37.3% - Simple routing responses, acknowledgments
- **Medium (2-10s):** 52.4% - Standard conversations
- **Slow (> 10s):** 10.3% - Complex queries requiring knowledge base searches

**Time Breakdown:**
- **Request-Manager overhead:** 0.012s (0.3%)
  - Session lookup, request normalization, database writes
- **Event delivery:** ~0.000s (negligible)
  - CloudEvent publish to broker
- **Agent processing:** 4.574s (99.7%)
  - Knowledge base lookup (0-15s depending on query)
  - LLM inference (2-5s typical)
  - State machine operations (< 0.1s)

**Key Finding:** 99.7% of request time is spent in agent processing (Llama Stack inference). The request-manager, event delivery, and response handling add negligible overhead (~12ms total). The key point is that efforts to scale implementations based on the quickstart should likely start by focussing on the LLM inference serving performance. While in production you should plan for a model with better performance, it is still likely that the largest component of the response time and CPU usage will be the LLM inference.

### Concurrency Model

All services handle requests concurrently using Python's asyncio event loop, even with a single uvicorn worker. This is a very efficient pattern and allows each component to handle many concurrent requests even with a single worker. If you want to learn more about asyncio check out [Python's asyncio: A Hands-On Walkthrough](https://realpython.com/async-io-python/)

**How it works:**
- Request handlers use `await` to yield control to the event loop
- While waiting for I/O (database, HTTP calls, agent responses), the event loop processes other requests
- Multiple requests can be "in flight" simultaneously without blocking each other

Asyncio is a great fit for this quickstart as we've seen that most of the time a request will be waiting for a response during LLM inference.

## Infrastructure Scaling

### Quickstart components

Use standard kubernetes scaling techniques. For agent-service, integration-dispatcher, request-manager, mock-eventing, you can scale the number of uvicorn workers as well as the number of replicas. For MCP servers (such as snow) the same is true, but special considerations which are covered in a later section. Both the number of workers and number of replicas can be configured in helm/values.yaml. As an example this snippet which is part of the configuration for the agent service sets 4 workers and 2 replicas:

```
 agentService:
    replicas: 2
    uvicornWorkers: 4  # Number of uvicorn worker processes for handling concurrent requests
```

In addition, autoscaling can also be configured to scale up the number of pods as load increases.

These are a few documents which may be of interest:

- [Scalability and performance | OpenShift Container Platform 4.20 Documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/scalability_and_performance/index)
- [Capacity management and overcommitment best practices in Red Hat OpenShift](https://www.redhat.com/en/blog/capacity-management-overcommitment-best-practices-openshift)

The quickstart already uses 4 unicornWorkers for each of the components. If you would like to try out multiple pods for each of the components you can set `REPLICA_COUNT` to set the number of pods to use. For example:

```
make helm-install-test REPLICA_COUNT=2 ....
```

### MCP Server Scaling (for example snow MCP server)

MCP servers often have state which can complicate scaling. For example the default transport for FastMCP is sse
which maintains state.

This quickstart uses streamable-http with stateless http to keep the server stateless. By using this combination scaling
is possible both with uvicorn worker and multiple pod replicas.

### Llama Stack

LlamaStack can be scaled horizontally using multiple replicas. **Important: You must configure PostgreSQL-backed storage for multi-replica deployments** to ensure resources like knowledge bases are shared across all replicas. This is done in the quickstart helm/values.yaml with:

```
  # Configure metadata store to use PostgreSQL for multi-replica support
  metadataStore:
    type: postgres
    db_path: null  # Explicitly unset SQLite field
    host: ${env.POSTGRES_HOST:=pgvector}
    port: ${env.POSTGRES_PORT:=5432}
    db: ${env.POSTGRES_DBNAME:=rag_blueprint}
    user: ${env.POSTGRES_USER:=postgres}
    password: ${env.POSTGRES_PASSWORD:=rag_password}
    namespace: llamastack_registry

  # Configure vector_io kvstore to use PostgreSQL for multi-replica support
  vectorIOKvstore:
    type: postgres
    db_path: null  # Explicitly unset SQLite field
    namespace: llamastack_vector_io
    host: ${env.POSTGRES_HOST:=pgvector}
    port: ${env.POSTGRES_PORT:=5432}
    db: ${env.POSTGRES_DBNAME:=rag_blueprint}
    user: ${env.POSTGRES_USER:=postgres}
    password: ${env.POSTGRES_PASSWORD:=rag_password}

  providers:
    agents:
      - provider_id: meta-ref-postgres
        provider_type: inline::meta-reference
        config:
          persistence_store:
            type: postgres
            namespace: null
            host: ${env.POSTGRES_HOST:=pgvector}
            port: ${env.POSTGRES_PORT:=5432}
            db: llama_agents
            user: ${env.POSTGRES_USER:=pgvector}
            password: ${env.POSTGRES_PASSWORD:=pgvector}
          responses_store:
            type: postgres
            host: ${env.POSTGRES_HOST:=pgvector}
            port: ${env.POSTGRES_PORT:=5432}
            db: llama_responses
            user: ${env.POSTGRES_USER:=pgvector}
            password: ${env.POSTGRES_PASSWORD:=pgvector}
```

These are a few documents which may be of interest:

- [Llama Stack Kubernetes Operator - Quick Start](https://llama-stack-k8s-operator.pages.dev/getting-started/quick-start/)
- [Deploying Llama Stack on Kubernetes](https://llama-stack-k8s-operator.pages.dev/how-to/deploy-llamastack/)

### PostgreSQL Database

Use standard PostgreSQL scaling techniques. These are a few documents which may be of interest:

- [PostgreSQL High Availability and Replication](https://www.postgresql.org/docs/current/high-availability.html)
- [Crunchy Data PostgreSQL on Red Hat OpenShift Container Storage](https://www.redhat.com/en/blog/crunchy-data-postgresql-red-hat-openshift-container-storage)

### Kafka (Production Eventing Mode)

Use standard Kafka scaling techniques. These are a few documents which may be of interest:

- [Chapter 20. Scaling clusters by adding or removing brokers](https://docs.redhat.com/en/documentation/red_hat_streams_for_apache_kafka/3.0/html/deploying_and_managing_streams_for_apache_kafka_on_openshift/assembly-scaling-kafka-clusters-str)
- [Red Hat AMQ Streams (Kafka on OpenShift)](https://access.redhat.com/documentation/en-us/red_hat_amq_streams)
- [Knative Eventing with Kafka](https://docs.openshift.com/serverless/latest/eventing/event-sources/knative-event-sources.html#knative-event-sources-kafka)

### LLM inference serving

Use standard LLM inference optimization techniques such as GPU acceleration, model quantization, and batching. These are a few documents which may be of interest:

- [Meet vLLM: For faster, more efficient LLM inference and serving](https://www.redhat.com/en/blog/meet-vllm-faster-more-efficient-llm-inference-and-serving)
- [Accelerate AI inference with vLLM](https://www.redhat.com/en/blog/accelerate-ai-inference-vllm)
- [vLLM - Optimization and Tuning](https://docs.vllm.ai/en/latest/configuration/optimization.html)
- [Red Hat Developers - OpenShift AI Learning](https://developers.redhat.com/learn/openshift-ai)
