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

Use standard kubernetes scaling techniques. For agent-service, integration-dispatcher, request-manager, mock-eventing, you can scale the number of uvicorn workers as well as the number of replicas. For MCP servers (such as snow) you must use 1 uvicorn worker and scale the number of replicas. Both the number of workers and number of replicas can be configured in helm/values.yaml. As an example this snippet which is part of the configuration for the agent service set the workers to 4, starts with 1 replica and allows scaling up to 5 replicas as load increases:

```
 agentService:
    replicas: 1
    uvicornWorkers: 4  # Number of uvicorn worker processes for handling concurrent requests

...

    autoscaling:
      enabled: false
      minReplicas: 1
      maxReplicas: 5
      targetCPUUtilization: 70
      targetMemoryUtilization: 80
```

These are a few documents which may be of interest:

- [Scalability and performance | OpenShift Container Platform 4.20 Documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/scalability_and_performance/index)
- [Capacity management and overcommitment best practices in Red Hat OpenShift](https://www.redhat.com/en/blog/capacity-management-overcommitment-best-practices-openshift)


### Llama Stack

Use standard kubernetes scaling techniques. These are a few documents which may be of interest:

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
