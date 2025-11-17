# 🛡️ Self-Service Agent Security Overview

This document outlines the security posture of the Self-Service Agent system. It is divided into two sections:

- **Current Security Strengths:** Describes the main security features that form the foundation of the system’s safety.
- **Production Hardening Requirements:** Checklist of mandatory configurations and controls to review and implement before production.

## Current Security Strengths


### 1. API Endpoints & Authentication

#### API Authentication - Web and CLI Endpoints
Web (`/api/v1/requests/web`) and CLI (`/api/v1/requests/cli`) endpoints require authentication before processing requests. Authentication is automatically validated for every request, and the authenticated user must match the request `user_id` to prevent privilege escalation. Invalid or missing authentication immediately returns 401 Unauthorized without executing any business logic.

#### Slack Signature Verification
Slack webhook endpoints (`/slack/events`, `/slack/interactive`, `/slack/commands`) verify Slack request signatures using HMAC-SHA256. This prevents unauthorized requests from non-Slack sources, validates timestamps and uses the Slack signing secret stored securely in Kubernetes Secrets. Invalid requests are rejected with a 403 Forbidden error.

#### Tool API Key Authentication
The tool endpoint (`/api/v1/requests/tool`) requires API key authentication via `x-api-key` header. API keys are stored in Kubernetes Secrets and ensuring least-privilege access for each tool. Invalid API keys return 401 Unauthorized.

#### Input Validation with Pydantic Schemas
API endpoints use Pydantic schemas to validate and sanitize request data. This strictly enforces data types, field length limits, and valid enum values (like IntegrationType), rejecting malformed requests before they reach any business logic.

---

### 2. Service Boundaries & Network Security

#### Network Policies for Service Isolation
Network policies are enabled to restrict network traffic between services and namespaces. The agent service is configured to only accept traffic from authorized sources (eventing infrastructure and same-namespace services), preventing unauthorized cross-namespace access. Port restrictions limit network exposure to only the necessary ports required for service communication.

#### Container Images Run as Non-Root
All Containerfiles drop privileges to non-root user (`USER 1001`) before running the application. This prevents applications from modifying system files or installing packages, reduces the impact of container escape vulnerabilities, and follows container security best practices. Multi-stage builds minimize the attack surface.

#### CloudEvent Atomic Processing
The integration dispatcher uses atomic event claiming to prevent duplicate processing across pods. This prevents race conditions in multi-pod deployments, database-level locking ensures only one pod processes each event, and it prevents duplicate deliveries and potential abuse.

#### External Route Configuration
Services follow the principle of least privilege for external exposure. The integration dispatcher has external access enabled by default only for incoming webhooks (required for external integrations), while the request manager remains cluster-internal by default and is only exposed externally when needed. This configuration prevents external access to unauthenticated endpoints. All external routes use proper TLS termination, and webhook endpoints are protected by signature verification (HMAC-SHA256).


---

### 3. Secrets & Credentials Management

#### Secrets Stored in Kubernetes Secrets
All sensitive credentials (API keys, Slack tokens, email passwords) are stored in Kubernetes Secrets rather than in code, and are namespace-scoped to limit exposure.

#### Database Connection Security
Database connections use connection pooling with configurable timeouts and connection limits. Statement timeouts and idle transaction timeouts are enforced at the database connection level to prevent long-running queries and resource exhaustion. Connection pooling includes pre-ping verification and automatic connection recycling to maintain healthy database connections.
---

### 4. Infrastructure & Deployment

#### Service Account Configuration
Service accounts are created with configurable automount setting by default. Service accounts are namespace-scoped, automount can be disabled if not needed, no excessive permissions are granted by default, and RBAC can be configured separately.

#### Multi-Stage Container Builds
All Containerfiles use multi-stage builds to minimize final image size. This reduces the attack surface by excluding build tools from production images, smaller images have fewer vulnerabilities, only runtime dependencies are included in the final image, and build dependencies are not accessible in production.

#### Dependency & Supply Chain Security
All services use `pyproject.toml` for dependency definition and `uv sync --frozen` to enforce exact, pinned dependency versions from `uv.lock`. This prevents supply chain attacks by blocking unauthorized dependency updates, ensures reproducible builds across environments, and locks all transitive dependencies to specific versions. Builds fail if dependency versions don't match the lock file.

---

### 5. Content Safety & Moderation

#### Content Safety Shields (Llama Guard)
There is an option to deploy with Safety Shield Configuration. Safety shields provide content moderation for AI agent interactions, validating user input and agent responses against safety policies using Llama Guard 3 or compatible models. This prevents harmful or non-compliant content from being processed or delivered, reducing the risk of unsafe outputs or malicious input.

---

### 6. Observability & Auditability

#### Structured Logging & Tracing
All services use structured logging and OpenTelemetry tracing for end-to-end visibility across service boundaries. This provides comprehensive observability for security auditing, incident response, and compliance requirements.

---

## Production Configuration Requirements

The following configurations must be changed from their development defaults to secure the system for production. This section focuses on **configuration changes** that need to be made before going live.

**Workflow with SECURITY_ACTION_ITEMS.md:**
- **SECURITY_ACTION_ITEMS.md** tracks security issues that require **code fixes or implementation work**
- Once an item from ACTION_ITEMS is fixed:
  - If it's now secure by default → add it to **Current Security Strengths** section above
  - If it requires configuration changes → add it to this **Production Requirements** section

## 1. API Endpoints & Authentication

### JWT Authentication (Currently Disabled)
**Current State:** JWT authentication is disabled by default (`security.jwt.enabled: false`). Implementation is incomplete - signature verification is missing.

**Production Requirement:**
- **Do NOT enable JWT** - Use API Key authentication for production (recommended)

---

## 2. Service Boundaries & Network Security

### Container Security Context
**Current State:** Security context settings (`runAsNonRoot`, `seccompProfile`, `capabilities.drop`) are commented out in `helm/values.yaml` as examples, not enabled by default. The capability is documented in the Helm templates but requires explicit configuration.

**Production Requirement:**
Enable security context settings in `helm/values.yaml` or production values file:
```yaml
podSecurityContext:
  runAsNonRoot: true

securityContext:
  capabilities:
    drop:
    - ALL
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 1001
```

**Note:** Container images already run as non-root user (`USER 1001`) by default in the Containerfiles, which is a current security strength. The pod security context provides additional enforcement at the Kubernetes level.

### Kafka Security Configuration
**Current State:** Kafka uses `PLAINTEXT` protocol (no encryption, no authentication). Kafka is configured as internal only (`type: internal`).

**Security Risk:** NOT NECESSARILY a direct security issue for external attackers

**Production Requirement:**
Set secure Kafka configuration in `helm/values.yaml`:
```yaml
requestManagement:
  knative:
    kafka:
      security:
        protocol: "SASL_SSL"
        sasl:
          enabled: true
          mechanism: "SCRAM-SHA-512"
          user: "kafka-user"
          secretName: "kafka-credentials"
          secretKey: "password"
```
---

## 3. Secrets & Credentials Management

### Secrets in Deployment Commands
**Current State:** Secrets are passed via `--set` flags in Helm deployment commands, exposing them in shell history, Helm history, and process lists.

**Security Risk:** YES - Secrets visible in multiple places

**Production Requirement:**
- **Do NOT use `--set` flags for secrets in production**
- Use one of the following secure methods:
  1. **Values File** (recommended for quickstart)
     - Create `helm/values-secrets.yaml` (gitignored)
     - Use `helm install ... -f values-secrets.yaml`
     - Secrets not visible in shell history or process lists
  2. **Pre-create Kubernetes Secrets** (most secure)
     - Use `kubectl create secret` before Helm deployment
     - Reference secrets in Helm values without passing values
     - Already partially implemented for ServiceNow credentials
  3. **CI/CD Secret Injection** (production best practice)
     - Secrets injected by CI/CD system (e.g., Tekton, ArgoCD)
     - Never appear in user's shell or command history


### API Keys and Secrets Rotation
**Current State:** Rotation should be planned for production.

**Production Requirement:**
- Implement API key rotation process (recommended: every 90 days or per security policy)
- Rotate API keys immediately if exposure is suspected or confirmed
- Document rotation process and maintain rotation schedule
- Store API keys in external secret manager with rotation support

---

## 4. Features That Should Be Disabled in Production

### Mock Eventing Service
**Current State:** Mock eventing is enabled by default (`requestManagement.knative.mockEventing.enabled: true`) for development. Real Knative eventing is disabled (`requestManagement.knative.eventing.enabled: false`).

**Production Requirement:**
**CRITICAL** - Disable mock eventing and enable real Knative eventing in `helm/values-production.yaml`:
```yaml
requestManagement:
  knative:
    eventing:
      enabled: true  # Enable real Knative eventing
    mockEventing:
      enabled: false  # Disable mock service
```

### Test Integration
**Current State:** Can be enabled via `testIntegrationEnabled: false` (disabled by default).

**Production Requirement:**
- Ensure `testIntegrationEnabled: false` in production values

---

## 5. Observability & Data Privacy

### Content Safety Shields Configuration
**Current State:** Safety shields are disabled by default (`safety.model: ""` and `safety.url: ""` in `helm/values.yaml`).

**Production Requirement:**
For high-risk or public-facing deployments, configure `safety.model` and `safety.url` in `helm/values.yaml` to enable content safety shields. See [`guides/SAFETY_SHIELDS_GUIDE.md`](../guides/SAFETY_SHIELDS_GUIDE.md) for detailed configuration instructions.


#### Sensitive Data Exposure in Observability Traces

**Current State:** Sensitive PII data (employee names, business justifications, email addresses) is captured in OpenTelemetry trace span attributes and application logs. PII masking/redaction is **disabled by default** for quickstart deployments to enable development and debugging, but **must be enabled for production** to comply with privacy regulations and protect sensitive data.

---

## 6. Infrastructure & Deployment

### Service Permissions & RBAC

**Admin Decision:** Services are designed to run with minimum (least-privilege) permissions and adapt to cluster configuration. Services use restrictive container-level security (`runAsNonRoot`, `capabilities.drop: ALL`) and successfully deploy to OpenShift namespaces with the most restrictive Security Context Constraints (SCCs). In standard Kubernetes clusters (e.g., kind), services may deploy with more elevated permissions depending on cluster configuration. This is acceptable and should be configured by the cluster admin according to organizational security policies.

### Image Tags
**Current State:** Default tag is `0.0.2` (specific version).

**Production Requirement:**
- Always use specific version tags (e.g., `v1.2.3`, `0.0.2`) - never use `latest` tag
- Update the tag to the latest stable version when deploying updates
- Ensure the tag matches the tested and approved image version

---