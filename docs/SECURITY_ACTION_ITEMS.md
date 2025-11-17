# Security Action Items

---

| # | Issue | Security Issue? | Section |
|---|-------|----------------|---------|
| 1 | Generic endpoint `/api/v1/requests/generic` without authentication | YES | [Generic Endpoint Without Authentication](#generic-endpoint-without-authentication) |
| 2 | Health check `/health` endpoint without authentication | NO | [Health Check Endpoints](#health-check-endpoints) |
| 3 | Health check `/health/detailed` endpoint exposes service information | MAYBE | [Health Check Endpoints](#health-check-endpoints) |
| 4 | CloudEvents endpoint `/api/v1/events/cloudevents` without authentication | YES | [CloudEvents Endpoint Without Authentication](#cloudevents-endpoint-without-authentication) |
| 5 | Missing network policies for critical services | YES | [Missing Network Policies for Critical Services](#missing-network-policies-for-critical-services) |
| 6 | Missing auth layer between Knative triggers and services | YES | [Missing Auth Layer Between Triggers and Services](#missing-auth-layer-between-triggers-and-services) |
| 7 | Secrets exposed in deployment commands (--set flags) | YES | [Secrets Exposed in Deployment Commands](#secrets-exposed-in-deployment-commands) |
| 8 | No secret rotation mechanism | MAYBE | [No Secret Rotation Mechanism](#no-secret-rotation-mechanism) |
| 9 | CLI access uses unauthenticated endpoint | YES | [CLI Access Uses Unauthenticated Endpoint](#cli-access-uses-unauthenticated-endpoint) |
| 10 | Information leakage via logging (INFO/WARNING/DEBUG levels) | MAYBE | [Information Leakage via Logging](#information-leakage-via-logging-infowarningdebug-levels) |
| 11 | Sensitive data exposure in observability traces | YES | [Sensitive Data Exposure in Observability Traces](#sensitive-data-exposure-in-observability-traces) |

---

## 1. API Endpoints & Authentication

#### Generic Endpoint Without Authentication

- **Risk:** YES
- **Issue:** Endpoint `/api/v1/requests/generic` has no authentication and accepts requests from any source
- **Current Mitigation:** Endpoint is not externally accessible (no external ingress/route), requires k8s internal network access
- **Security Concern:** Endpoint is accessible by any pod/container in the cluster with network access (not just pod exec permissions)
- **Options:**
  1. **Disable endpoint in production mode** (recommended)
     - Add feature flag to disable `/api/v1/requests/generic` when in production
     - This may be sufficient to mitigate the security vulnerability
  2. Add `Depends(get_current_user)` dependency (same as `/api/v1/requests/web` and `/api/v1/requests/cli`)

#### Health Check Endpoints Without Authentication

**`/health` Endpoint:**
- **Risk:** NO
- Lightweight operation, no database access


#### health/detailed Endpoint Without Authentication
**`/health/detailed` Endpoint :**
- **Risk:** MAYBE
- Performs database queries and returns service information (version, database status, integrations list) without authentication

#### CloudEvents Endpoint Without Authentication

- **Risk:** YES
- **Issue:** Endpoint `/api/v1/events/cloudevents` has no authentication and accepts events from any source
- **Current State:** Endpoints are called by Knative triggers (internal cluster traffic via `.svc.cluster.local`)
- Ensure endpoints remain internal only at all times

---

## 2. Service Boundaries & Network Security

#### Missing Network Policies for Critical Services
**Issue:** Multiple critical services lack proper network policies for internal isolation.

- **Risk:** YES
- **Current State:**
  - **Request-manager and integration-dispatcher:** No network policies defined
  - **agent-service:** Has partial network policy (allows traffic from `knative-eventing` namespace and same namespace), but any pod in the same namespace can access it
  - **mcp-servers:** No network policies defined - accessible by any pod/container in the cluster
  - **agent-service calls mcp-servers:** Agent service needs access to mcp-servers, but currently any service can also call mcp-servers
- **Security Concern:**
  - If a pod in the cluster is compromised, it can directly call mcp-servers, agent-service, or other services
  - No verification that requests come from authorized services (agent-service should be the only caller of mcp-servers)
  - Network policies provide defense in depth - even if attacker has cluster access, they limit lateral movement
  - **Add Network Policies** 
     - **mcp-servers:** Restrict ingress to only allow traffic from agent-service pods (use `podSelector` with agent-service labels)
     - **agent-service:** Restrict ingress to only allow traffic from:
       - Knative eventing namespace (for CloudEvents)
       - Request-manager service pods (for direct API calls, use `podSelector`)
       - Avoid allowing all pods in same namespace - use specific `podSelector` instead of `namespaceSelector`
     - **request-manager and integration-dispatcher:** Add network policies to restrict ingress to authorized sources only
     - Example: Use `podSelector` with specific labels instead of `namespaceSelector` for tighter control

#### Missing Auth Layer Between Triggers and Services
**Issue:** Knative triggers call service endpoints (`/api/v1/events/cloudevents`) without authentication layer.

- **Risk:** YES
- **Current State:** Triggers use internal cluster DNS (`.svc.cluster.local`) but no authentication/authorization
- **Potential Issues:**
  - If cluster is compromised, attacker could inject events directly to services
  - No verification that events actually come from authorized Knative triggers
- **Options:**
  1. **Implement Knative Authorization** (recommended)
     - Use Knative's built-in authorization features: https://knative.dev/docs/eventing/features/authorization/
     - Configure OIDC or service account-based authentication between triggers and subscribers
  2. **Network Policies** (defense in depth)
     - Restrict ingress to CloudEvents endpoints from `knative-eventing` namespace only
     - Already partially implemented for agent-service (see `helm/templates/network-policies.yaml`)
     - Extend to request-manager and integration-dispatcher
  3. **Both** (most secure)
     - Combine Knative authorization + network policies for layered security

---

## 4. Secrets & Credentials Management

#### Secrets Exposed in Deployment Commands
**Issue:** Secrets are passed via `--set` flags in Helm deployment commands, exposing them in shell history, Helm history, and process lists.

- **Risk:** YES
- **Current State:** Most secrets passed via `--set`/`--set-string` flags in Makefile. ServiceNow credentials use Pre-created Secrets approach: values passed to `kubectl create secret` (via environment variables), then only secret name passed to Helm via `--set`.
- **Exposure Points:** Shell history, Helm release history, process lists (`ps aux`), system logs
- **Security Concern:** Secrets visible to anyone with access to shell history, Helm history, or process lists
- **Comparison:**
  | Method | ps aux | Shell History | Helm History | Security Level |
  |--------|--------|---------------|--------------|----------------|
  | Current (--set) | ❌ Yes | ❌ Yes | ❌ Yes | 🔴 Low |
  | Values File | ✅ No | ✅ No | ❌ Yes | 🟡 Medium |
  | Pre-created Secrets* | ✅ No | ✅ No** | ✅ No | 🟢 High |
  | --set-file | ✅ No | ✅ No | ❌ Yes | 🟡 Medium |
  | CI/CD Injection | ✅ No | ✅ No | ❌ Yes | 🟢 High |
  
  \* Pre-created Secrets: Use environment variables or `--from-file` when creating secrets to avoid shell history exposure  
  \** Shell history: Safe when using environment variables (e.g., `$SECRET_KEY`) or CI/CD, not when passing values directly

- **Note:** After checking other quickstarts, they use both `--set` and `values-secrets.yaml` files. Each project uses one approach as primary, with the other as optional. 

#### No Secret Rotation Mechanism
**Issue:** No automated secret rotation process documented or implemented.

- **Risk:** Long-lived secrets increase exposure risk like ServiceNow API KEY
- **Action:**
  - Document rotation process
  - Implement automation (External Secrets Operator with rotation)
  - Add monitoring/alerting for expiration

---

## 5. Features That Should Be Disabled in Production

#### CLI Access Uses Unauthenticated Endpoint

**Issue:** CLI client uses unauthenticated `/api/v1/requests/generic` endpoint. Request Manager external access disabled by default (`externalAccess.enabled: false`).

**Options:**
1. **Disable CLI in production** (recommended)
   - Keep `externalAccess.enabled: false`

2. **Fix CLI authentication**
   - Change line 226: `endpoint="generic"` to `endpoint="cli"`
   - Fix `endpoint="generic"`

#### Information Leakage via Logging (INFO/WARNING Levels)
**Issue:** Multiple services log sensitive information (PII, request/response bodies) at INFO/WARNING levels active in production.

**Risk:** NOT NECESSARILY a security issue for external attackers

1. **ServiceNow Client - Full Request/Response Body Logging**
   - **File:** `mcp-servers/snow/src/snow/servicenow/client.py` lines 125, 134, 142
   - **Issue:** Logs complete request body, response body, and full response at INFO level

2. **Agent Service - Full Response Logging**
   - **File:** `agent-service/src/agent_service/session_manager.py` line 645
   - **Issue:** Logs complete agent response (`processed_response`) at INFO level

3. **Slack Service - Full User Info Logging**
   - **File:** `integration-dispatcher/src/integration_dispatcher/slack_service.py` line 619
   - **Issue:** Logs complete `user_info` object at WARNING level

4. **Request Manager - Integration Context Logging**
   - **File:** `request-manager/src/request_manager/main.py` line 933
   - **Issue:** Logs complete `integration_context` with `slack_user_id`, `slack_channel`, `email_from`

#### Sensitive Data Exposure in Observability Traces

**Risk:** YES

**The Problem:**
Sensitive PII (Personally Identifiable Information) from MCP servers is captured in both OpenTelemetry traces and general logging. This includes employee names, business justifications, and email addresses that get stored in trace data and log files, making them visible in observability tools (Jaeger, Grafana Tempo, etc.) and log aggregation systems.

**Where it happens:**
- **Traces:** `mcp-servers/snow/src/snow/tracing.py` - Function parameters saved as span attributes
- **Logs:** Multiple services log sensitive data at INFO/WARNING levels (see "Information Leakage via Logging" section above)


| Data Type | Location | Captured In Traces? | Risk Level | Action Needed |
|------------------------|---------------------|-----------------------|----------|------------------------------------------|
| Employee Names | MCP tool args | ✅ YES (span attributes) | ⚠️ Medium | Redact or disable for sensitive use cases |
| Business Justifications | MCP tool args | ✅ YES (span attributes) | ⚠️ Medium | Redact or disable for sensitive use cases |
| Email Addresses | authoritative_user_id | ✅ YES (span attributes) | ⚠️ Medium | Redact or disable |
| Laptop Codes | MCP tool args | ✅ Yes | ✅ Low | Acceptable |
| API Keys/Tokens | Auth headers | ❌ No | ✅ None | Safe |
| Passwords | N/A | ❌ No | ✅ None | Safe |
| Request/Response Bodies | HTTP calls | ❌ No | ✅ None | Safe |
| HTTP Headers | Auto-instrumentation | ❌ No (not configured) | ✅ None | Safe |
| Trace IDs | traceparent | ✅ Yes | ✅ None | Safe (not sensitive)


**Proposed Solution:**
Implement a configurable option to mask/redact sensitive data (employee name, business justification, email address) from both traces and logs. This option should:
- Be **disabled by default** for quickstart deployments (enables development/debugging)
- Be **enabled by default** or explicitly configured for production deployments.