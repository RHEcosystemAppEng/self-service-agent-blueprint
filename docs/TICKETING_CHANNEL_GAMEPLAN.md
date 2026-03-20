# Ticketing Channel: Game Plan

**Status**: **Phase 0 and 0.5 are fully implemented in-repo** (Zammad Helm deploy, undeploy, values, Route/embed, `helm-install-ticketing`, token/bootstrap helpers). What remains is **operator work** (finish autoWizard if needed, confirm secret/token) and later **Phase 1+** application code.  
**Branch**: `zammadHelm`  
**Last updated**: 2026-03-20

---

## 1. Branch Audit Summary

### What Changed (ticketingChannel vs dev)

| Category | Details |
|----------|---------|
| **Commits** | 7 commits, all titled "zammad" |
| **Code changes** | **None** — documentation only |
| **Files added** | 3 docs (gameplan + 2 supporting; see below) |

### New Documents

| Document | Purpose |
|----------|---------|
| `MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md` | Meeting outcomes: login, point-first, A-to-Z, safeguards, escalation |
| `ZAMMAD_TICKETING_CHANNEL_PLAN.md` | Full Zammad technical reference (payloads, MCP tools, phases) |

### Key Decision: Zammad

Zammad is the ticketing channel because it provides:

- Purpose-built helpdesk
- Built-in chat widget (no custom UI)
- Straightforward webhooks and official Helm chart
- Mature community MCP (basher83/Zammad-MCP)

---

## 2. Implementation Touchpoints (from Audit)

All references verified against current codebase. *Note: Line numbers approximate; reqMgrOrder rebase altered request-manager structure (session_orchestrator, etc.).*

| Component | Location | Current State | Required Change |
|-----------|----------|----------------|-----------------|
| **IntegrationType enum** | `shared-models/.../models.py` (L51–64) | SLACK, WEB, CLI, TOOL, EMAIL, SMS, WEBHOOK, TEAMS, DISCORD, TEST | Add `ZAMMAD` |
| **Request schemas** | `request-manager/.../schemas.py` | SlackRequest, WebRequest, CLIRequest, EmailRequest, ToolRequest | Add ZammadRequest |
| **Request Manager handler** | `request-manager/.../main.py` (L636–746) | Branches for SLACK, EMAIL | Add branch for ZAMMAD |
| **Normalizer** | `request-manager/.../normalizer.py` | Handles Slack/Web/CLI/Email/Tool | Add `_normalize_zammad_request`; set `target_agent_id="ticket-resolution-agent"`, `requires_routing=False` |
| **Integration Dispatcher** | `integration-dispatcher/.../main.py` | Slack routes, Email (IMAP) | Add `POST /zammad/webhook` |
| **Webhook services** | `integration-dispatcher/` | slack_service, email_service | Add zammad_service |
| **Helm MCP blocks** | `helm/values.yaml` | self-service-agent-snow | Add zammad-mcp |
| **Agent config** | `agent-service/config/agents/` | laptop-refresh-agent, routing-agent | Add `ticket-resolution-agent.yaml` |
| **Agent Service** | `agent-service/.../main.py`, `session_manager.py` | Ignores `target_agent_id`; always creates routing-agent sessions | Pass `target_agent_id` and `requires_routing` to session manager; when set, create specialist session directly |

**DB migration:** Adding enum values to PostgreSQL `IntegrationType` requires an Alembic migration (used in `UserIntegrationConfig`, `RequestLog`, etc.).

### 2.0 Rebase: reqMgrOrder (Session Serialization)

*Rebased on reqMgrOrder; 3 commits: session request serialization, retry docs, legacy resolver.*

**Migration chain:** Session serialization consolidated migrations into `001_consolidated_schema.py`. Our `002_add_zammad_integration_type.py` has `down_revision = "001"`. Migrations 002, 003 (old) were removed and consolidated; our Zammad migration is the new 002.

**Session serialization:** Zammad requests participate in the same FIFO/session-lock pipeline. `session_id="zammad-{ticket_id}"` is used as partition key for broker ordering. No Zammad-specific changes needed—flows through `session_orchestrator`, `RequestLog`, advisory lock like Slack/Email.

**Integration Dispatcher:** reqMgrOrder adds `outbox_publisher`, `thread_lock`, `outbox_metrics`. Phase 2 `zammad_service` should follow the same event-send pattern as `slack_service`/`email_service` (e.g. outbox for durable publish if they use it).

**Reference:** [SESSION_SERIALIZATION_RUNBOOK.md](SESSION_SERIALIZATION_RUNBOOK.md) — ordering, partition keys, reclaim, 503 behavior. Zammad aligns with existing model.

### 2.1 ZammadRequest Schema & event_data Structure

**ZammadRequest fields** (per [ZAMMAD_TICKETING_CHANNEL_PLAN.md](ZAMMAD_TICKETING_CHANNEL_PLAN.md)):

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `integration_type` | IntegrationType | yes | ZAMMAD |
| `user_id` | str | yes | From `customer_id`/`origin_by_id` mapping |
| `content` | str | yes | Article body (user message) |
| `ticket_id` | int | yes | Ticket ID for session continuity |
| `article_id` | int | yes | Article ID |
| `group_id` | int | yes | For allowlist check |
| `group_name` | str | no | Human-readable |
| `owner_id` | int | no | Ticket owner |
| `created_by_id` | int | yes | Article creator (for feedback-loop filter) |
| `zammad_delivery_id` | str | yes | From X-Zammad-Delivery header; idempotency |
| `request_type` | str | yes | e.g. `zammad_ticket_article` |
| `metadata` | dict | no | Additional context |

**event_data** (what `zammad_service` must produce for `send_request_event`):

```python
{
    "user_id": str,                    # Required
    "content": str,                   # Article body
    "integration_type": "ZAMMAD",
    "request_type": "zammad_ticket_article",
    "session_id": f"zammad-{ticket_id}",
    "metadata": {"ticket_id": int, "article_id": int, "group_id": int, ...},
    "integration_context": {"ticket_id": int, "article_id": int, "group_id": int, "zammad_delivery_id": str},
    "ticket_id": int,
    "article_id": int,
    "group_id": int,
    "created_by_id": int,
    "zammad_delivery_id": str,
}
```

### 2.2 Agent Service target_agent_id Flow (Critical)

**Current gap:** `agent-service/main.py` calls `session_manager.handle_responses_message(text, request_manager_session_id)` but does **not** pass `target_agent_id` or `requires_routing`. The session manager always creates a routing-agent session via `_create_initial_session`.

**Required change:**

1. **agent-service/main.py** `_handle_responses_mode_request`: Pass `target_agent_id=request.target_agent_id` and `requires_routing=request.requires_routing` to `handle_responses_message`.
2. **session_manager.py** `handle_responses_message`: Add params `target_agent_id`, `requires_routing`; pass to `_create_initial_session`.
3. **session_manager.py** `_create_initial_session`: When `target_agent_id` is set and `requires_routing=False`, create specialist session for that agent directly (skip routing-agent).

---

## 3. Meeting Notes Direction & Discussion Points

Per [MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md](MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md).

### Agent Capabilities (Aligned Outcomes)

| Capability | Direction |
|------------|-----------|
| **Login & conversation** | Users can start new tickets or continue existing ones; session continuity via `ticket_id` |
| **Point-first** | When docs or open tickets address the query, point users there rather than open new tickets |
| **A-to-Z resolution** | Some scenarios resolvable end-to-end (e.g., "What's the printer?"); agent asks "Has this resolved your issue?" → close ticket if yes |
| **Safeguards** | KB content + shields (LlamaStack); promptguards for controlled scenarios (e.g., Windows laptop request — approval authority TBD) |
| **Escalation** | Mechanism for human intervention; Zammad MCP supports (`zammad_add_article`, `zammad_update_ticket`) |
| **Agent on existing tickets** | Later phase: Zammad Time Event trigger preferred (e.g., "Ticket Pending Time Reached" → webhook → agent adds resolution via MCP); no CronJob |

### Knowledge Base

- **Source:** Static files only; no Zammad wiki sync
- **Path:** `agent-service/config/knowledge_bases/ticket-resolution/` — .txt files
- **Pipeline:** Existing quickstart pipeline (RAG via LlamaStack vector store)
- **Agent reference:** `knowledge_bases: ["ticket-resolution"]`

### Discussion Points (Open / TBD)

- Escalation flow: trigger logic, state names, owner resolution
- Promptguards: Windows laptop approval authority (manager vs IT manager per request tier)
- Zammad Time Event trigger for idle tickets — later phase

---

## 4. Possibilities & Trade-offs

### 4.1 Phase Ordering

**Meeting notes alignment:** Per [MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md](MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md), the meeting specified: Phase 1 = Deploy Zammad instance first; Phase 2 = Deploy MCP, wire to agent; Phase 3 = Webhook route; Phase 4 = Chat widget; Phase 5 = Helm integration.

**Quickstart scope:** The quickstart assumes **Zammad is already deployed** (or teams bring their own). Quickstart phases focus on webhook + MCP integration, not Zammad deployment.

**Quickstart phases:**

0. **Prerequisite:** Deploy Zammad instance via Helm (`zammad.enabled`, `make deploy-zammad`, or external) — needed to test MCP and webhooks as we progress
1. Deploy MCP + agent config (ticket-resolution-agent)
2. Webhook route + IntegrationType + schemas + normalizer
3. Chat widget setup (AI agent user, availability)
4. Demo seed data, Helm integration

**Recommendation:** Stick with plan order — MCP without incoming requests is hard to validate end-to-end. Webhook in Phase 2 gives a real trigger.

---

### 4.2 Outgoing Delivery: MCP Only

Ticketing differs from Slack/Email: the agent delivers replies directly via MCP (`zammad_add_article`), not through the Integration Dispatcher. However, the delivery pipeline may still receive delivery requests for Zammad sessions (e.g. from response events). The dispatcher's `handlers` dict requires a handler for each `IntegrationType` it may encounter—otherwise it raises `ValueError("No handler for integration type: ZAMMAD")`.

**Implication:** Add a **no-op `ZammadIntegrationHandler`** that immediately returns success without delivering. The agent has already posted via MCP; this avoids dispatch errors when ZAMMAD appears in user configs or delivery context.

---

### 4.3 Alembic Migration Strategy

`IntegrationType` is stored in DB (enum column). Adding new values:

- PostgreSQL: `ALTER TYPE integrationtype ADD VALUE 'ZAMMAD'`
- Alembic: Migration that runs the `ALTER TYPE` for each new value
- Order: Add migration in same PR as IntegrationType code change, or in a preceding migration-only PR

---

## 5. Proposed Implementation Roadmap

*Phase ordering vs. meeting notes: See [Section 4.1](#41-phase-ordering). Quickstart phases assume Zammad is available.*

### PR Strategy — Usable Functionality Per PR

Each PR delivers something testable and working:

| PR | Scope | Usable outcome | How to verify |
|----|-------|----------------|---------------|
| **PR 0** | Docs only | Planning docs on dev | Merge; no code change |
| **PR 1** | Phase 1 (Foundation) | Inject Zammad-like CloudEvent → agent processes → MCP | Unit tests + inject test event (or Request Manager integration test) |
| **PR 2** | Phase 2 (Webhook) | Real Zammad webhook → agent → MCP | POST mock payload to `/zammad/webhook`; E2E with Zammad instance |
| **PR 3** | Phase 3 (Chat & Seeding) | Chat widget demo | `make deploy-zammad` + chat; optional, can be follow-up |

**Phase 1 as one PR:** Foundation is kept as a single PR because splitting it (e.g. schema-only vs agent-only) would leave an intermediate state where Zammad events flow but the agent lacks the ticket-resolution agent and would fail. One PR ensures the first merge delivers end-to-end flow for injected events.

---

### Phase 0: Zammad Instance Deployment — Prerequisite

**Goal:** Deploy a Zammad instance for local/dev testing of MCP and webhooks (or use external Zammad).

**Implementation status:** All **automated** Phase 0 items below are done in this repository. The unchecked items are **not missing features**—they are steps a human (or your pipeline) performs against a live cluster.

- [x] `make deploy-zammad` — Helm install of official Zammad chart (`zammad/zammad` 16.0.4)
- [x] `make undeploy-zammad` — Remove Zammad from namespace (also runs during `helm-uninstall`)
- [x] `helm/values-zammad-deploy.yaml` — Optional overrides for dev deployment
- [x] **Helpers:** `zammad-trigger-autowizard`, `zammad-bootstrap-token`, `zammad-set-token`, `zammad-update-embed-url` (see `make help`)
- [ ] **Ops / manual:** Complete Zammad setup (autoWizard URL or Web UI), obtain API token — *required once per environment*
- [ ] **Ops / manual:** Ensure `zammad.url` and credentials Secret align with how you enable ticketing (`helm-install-ticketing` creates/patches the secret when possible)

**Zammad chart: autoWizard** — The official Zammad Helm chart supports `autoWizard.enabled` with a JSON config that can seed:
  - **Users** (admin: login, email, password, organization)
  - **Organizations**
  - **Settings** (e.g. product_name, system_online_service)
  - **Token** (for the autowizard URL itself; not the API token)

Example (`helm show values zammad/zammad`):
```yaml
autoWizard:
  enabled: false
  config: |
    {
      "Token": "secret_zammad_autowizard_token",
      "Users": [{"login": "admin@example.org", "firstname": "Admin", "lastname": "User", "email": "...", "organization": "Demo", "password": "..."}],
      "Organizations": [{"name": "Demo"}],
      "Settings": [{"name": "product_name", "value": "..."}]
    }
```

**API token:** Not configurable via autowizard JSON alone. **Implemented:** `make zammad-bootstrap-token` (and the token step inside `helm-install-ticketing`) calls the Zammad API from `zammad-railsserver` to create a token and updates the K8s secret. Manual path: Admin → Token Access → HTTP Token, then `make zammad-set-token`.

**Usage:** `make deploy-zammad NAMESPACE=my-namespace` (requires NAMESPACE). First deploy takes ~10–15 minutes (elasticsearch, postgresql, redis, memcached).

**Idempotency:** `deploy-zammad` is idempotent. If `--wait` times out (20m), re-run the same command—the release is already deployed; the next run will wait again and succeed once Zammad is ready. Worst case: zammad-init job may run again; init jobs are typically safe to re-run.

### Phase 0.5: One-Shot Ticketing Deploy (helm-install-ticketing)

**Goal:** Single-command deploy for ticketing dev/demo—mirrors `helm-install-demo` (email + Greenmail) pattern.

- [x] Add `helm-install-ticketing` Makefile target
- [x] Target flow: `deploy-zammad` → create zammad-credentials secret → `helm upgrade --install` main chart with `-f helm/values-ticketing.yaml` (zammad.enabled, zammad-mcp, envSecrets for ZAMMAD_URL/ZAMMAD_HTTP_TOKEN)
- [x] Print follow-up checklist (match deploy-zammad output):
  1. Get the Zammad URL (Route or port-forward)
  2. Complete initial setup at the Web UI (create admin, org, etc.)
  3. Create API token: Admin → Token Access → add HTTP Token
  4. Enable ticketing in quickstart: set `zammad.enabled=true`, `zammad.url`, create Secret with token
  5. (Optional) Configure webhook trigger (see Section 5.2)
- [x] Document in `make help` and HELM_EXPORT_ANSIBLE.md (or quickstart)

**Design / token chicken-and-egg:** Implemented **option (2) allow broken state** plus **automation**: autoWizard seeds admin; token creation runs via `kubectl exec` into `zammad-railsserver` (Ruby one-liner to call Zammad REST API). No external reachability required; always uses in-cluster exec.

### Phase 0 (legacy): Merge Docs (Ready Now)

- [ ] PR: Merge ticketingChannel into dev (docs only, no code risk)
- [ ] Outcome: Planning docs live on dev; team has single source of truth

### Phase 1: Foundation (Zammad) — PR 1 (deferred on `zammadHelm`)

**Dependency order:** shared-models (IntegrationType) → Alembic migration → request-manager, agent-service, helm. Integration Dispatcher Phase 2 depends on shared-models for IntegrationType.ZAMMAD.

- [ ] Alembic migration: Add `ZAMMAD` to IntegrationType enum (`002_add_zammad_integration_type.py`)
- [ ] shared-models: Add `ZAMMAD` to IntegrationType
- [ ] request-manager: Add ZammadRequest schema
- [ ] request-manager: Add ZAMMAD branch in CloudEvent handler
- [ ] normalizer: Add `_normalize_zammad_request`; set `target_agent_id="ticket-resolution-agent"`, `requires_routing=False`, `session_id="zammad-{ticket_id}"`; populate `integration_context` with `ticket_id`, `article_id`, `group_id`, `zammad_delivery_id` for agent use
- [ ] agent-service: Create ticket-resolution-agent.yaml (Zammad MCP + `knowledge_bases: ["ticket-resolution"]`); configure input/output shields (pattern: laptop-refresh-agent)
- [ ] agent-service: Pass `target_agent_id` and `requires_routing` from NormalizedRequest to session manager; when `target_agent_id` set and `requires_routing=False`, create specialist session directly (skip routing-agent)
- [ ] agent-service: Create `config/knowledge_bases/ticket-resolution/` with seed .txt files (SOPs, FAQs for RAG)
- [x] helm: Add `zammad-mcp` block to `mcp-servers.mcp-servers`; add `zammad` values block (see Section 5.1) — *done as part of Phase 0.5 / deploy wiring on this branch*
- [ ] integration-dispatcher: Add no-op `ZammadIntegrationHandler` (typically Phase 1 so delivery pipeline works when Zammad events are processed)
- [ ] **Deliverable:** Agent can receive ZammadRequests and process them (no webhook yet — test via mock/inject); unit test `test_normalize_zammad_request` added

**Agent config details:** File `agent-service/config/agents/ticket-resolution-agent.yaml` with `name: "ticket-resolution-agent"` (must match for `get_agent()`). MCP config: `uri` from Helm (`http://mcp-zammad:8000/mcp` or similar); `knowledge_bases: ["ticket-resolution"]`. Shields: pattern from `laptop-refresh-agent.yaml` (`input_shields`, `output_shields`, `ignored_input_shield_categories`).

### Phase 2: Incoming Webhook — PR 2

- [ ] integration-dispatcher: Add `POST /zammad/webhook` route
- [ ] integration-dispatcher: Add `zammad_service.py` (follow `slack_service`/`email_service` pattern—outbox, `send_request_event`, etc. per reqMgrOrder):
  - Parse Zammad trigger payload (`ticket`, `article` objects; payload structure in [ZAMMAD_TICKETING_CHANNEL_PLAN.md](ZAMMAD_TICKETING_CHANNEL_PLAN.md#technical-details))
  - Verify `X-Hub-Signature` (HMAC-SHA1 with `webhookSecret`); reject 401 if invalid
  - **Event filtering:** Process only ticket create + article create (customer/external); skip internal notes, agent articles
  - **Feedback-loop filter:** Skip when `article.origin_by_id` or `article.created_by_id` == `aiAgentUserId` (from `zammad.aiAgentUserId` Helm value)
  - **Group allowlist:** Only process when `ticket.group_id` in `zammad.allowedGroups` (empty = allow all)
  - Build `event_data` per Section 2.1; call `cloudevent_sender.send_request_event()`
- [ ] integration-dispatcher: **user_id derivation:** Use `ticket.customer_id` or `article.origin_by_id`; for v1 use synthetic `zammad-{customer_id}` unless UserIntegrationMapping supports ZAMMAD (customer email → canonical user)
- [ ] integration-dispatcher: **Idempotency:** Use `X-Zammad-Delivery` header as `event_id`; check `ProcessedEvent` table before sending (pattern: Slack/Email); skip if already seen; Zammad retries up to 4× on failure
- [ ] integration-dispatcher: Add no-op `ZammadIntegrationHandler` — *depends on Phase 1*
- [ ] **Deliverable:** Real Zammad webhook → Integration Dispatcher → Request Manager → Agent → MCP

### Phase 3: Chat Widget & Seeding — PR 3

- [x] Zammad instance deployment — *covered by Phase 0 (`make deploy-zammad` / `helm-install-ticketing`); use external Zammad instead if preferred*
- [ ] AI agent user in Zammad, Agent role, availability config (or "Leave a message" mode)
- [ ] Chat widget config in Zammad Admin (Channels → Chat); embed script on target site
- [ ] **Seeding** (see below)
- [ ] **Deliverable:** End-to-end demo: user sends chat → agent replies via MCP → reply in chat

---

### 5.1 Helm Values Structure

```yaml
# helm/values.yaml additions
zammad:
  enabled: false
  url: "https://zammad.example.com"   # MCP needs url + /api/v1
  webhookSecret: ""                    # From K8s Secret; HMAC key for X-Hub-Signature
  allowedGroups: []                    # Empty = allow all; e.g. [1, 3] = only groups 1, 3
  aiAgentUserId: null                 # Zammad user ID of AI agent; required for feedback-loop filter
  mcp:
    enabled: true
    uri: "http://mcp-zammad:8000/mcp"
    # Env from Secret: ZAMMAD_URL (url + /api/v1), ZAMMAD_HTTP_TOKEN
```

**MCP block** (add to `mcp-servers.mcp-servers`):
```yaml
zammad-mcp:
  enabled: true
  replicas: 1
  image:
    repository: ghcr.io/basher83/zammad-mcp
    tag: latest
  env:
    ZAMMAD_URL: "{{ .Values.zammad.url }}/api/v1"
    ZAMMAD_HTTP_TOKEN: "..."  # From Secret
    MCP_TRANSPORT: "http"
```

---

### Seeding Checklist

All components must be seeded for a working demo. Pattern: init jobs or `make deploy-zammad`-style targets.

| Component | What to seed | Location / mechanism |
|-----------|--------------|------------------------|
| **Knowledge bases** | Ticket-resolution KB content | `agent-service/config/knowledge_bases/ticket-resolution/*.txt` — SOPs, FAQs, known fixes (e.g., printer locations, common errors) |
| **Zammad instance** | Zammad stack (postgres, redis, app) | Helm subchart or `zammad/zammad-helm`; `make deploy-zammad` or `helm/values.yaml` `zammad.enabled` |
| **Zammad MCP** | Deployed, connected to Zammad API | Helm `zammad-mcp` block; `ZAMMAD_URL`, `ZAMMAD_HTTP_TOKEN` from Secret |
| **AI agent user** | Zammad user for AI; Agent role | Init job or manual; **record user ID** and set `zammad.aiAgentUserId` in Helm values — required for feedback-loop filter |
| **Groups** | Sample support groups | Init job or Zammad Admin; add group IDs to `zammad.allowedGroups` if restricting |
| **Sample tickets** | 1–2 demo tickets | Optional; for demo/testing; no GH sync (Zammad is not git-based) |
| **Webhook trigger** | Zammad trigger → POST `/zammad/webhook` | See Section 5.2 |

**KB content examples:** Printer locations, common error resolutions, "how to reset password" SOPs — enough for agent to demonstrate point-first and A-to-Z resolution.

**Zammad instance:** External Zammad — teams bring their own; quickstart adds webhook + MCP. Optional: deploy via Helm (`zammad.enabled` or `make deploy-zammad`) as Phase 1 prerequisite for local/dev validation (per meeting notes: deploy Zammad first).

### 5.2 Zammad Webhook Trigger Configuration

In Zammad Admin (Manage → Triggers):

1. **Create trigger:** e.g. "Ticket Article Created (Customer)"
2. **Conditions:** Ticket → Article → Created; Article → Sender → Customer (or External)
3. **Perform:** Webhook → URL: `https://<integration-dispatcher>/zammad/webhook`; Method: POST
4. **Secret:** Generate and store in K8s Secret; set in trigger for X-Hub-Signature
5. **Exclude:** Add condition to skip when article created by AI agent user (or rely on backend filter via `aiAgentUserId`)

Alternative: "Ticket Created" trigger for new tickets; "Article Created" for follow-up messages. Both POST to same endpoint.

### 5.3 Chat Widget Setup (for full flow understanding)

Enable Zammad's built-in chat to see the end-to-end flow: user sends chat → webhook → agent → MCP adds article → reply appears in chat.

1. **Channels → Chat:** Zammad Admin → Channels → Chat → Add website
2. **AI agent availability:** Chat widget appears only when an agent is available. Options:
   - Create a dedicated AI agent user (Agent role); keep it "online" or use triggers to auto-assign
   - Or use "Leave a message" mode: messages become tickets when no agent is online; agent processes asynchronously
3. **Embed:** Copy the widget script; embed on a test page (or use Zammad's preview)
4. **Flow:** User sends message → Zammad creates ticket + article → webhook fires (if trigger configured) → agent replies via MCP → reply appears in chat

Reference: [Zammad Chat docs](https://admin-docs.zammad.org/en/latest/channels/chat.html)

---

### Success Criteria

- [ ] Agent can read and update Zammad tickets via MCP
- [ ] New ticket or customer article triggers agent processing
- [ ] Agent reply posted as ticket article via MCP
- [ ] No feedback loop (agent's own articles ignored)
- [ ] Chat widget: user sends message → agent reply appears in chat
- [ ] Session continuity via `ticket_id`; multi-turn works (user article → agent article → repeat)
- [ ] Documented in README or quickstart guide

---

## 6. Security & Performance

### Security

| Item | Action |
|------|--------|
| Webhook signature | Verify X-Hub-Signature (HMAC-SHA1) with trigger secret; reject invalid; store secret in K8s Secret; never log |
| Group allowlist | Only process webhooks for tickets in configured groups (zammad.allowedGroups) |
| MCP token | Store ZAMMAD_HTTP_TOKEN in K8s Secret; never log or expose |
| Safety shields | Input/output shields on ticket-resolution-agent (see Phase 1) |

### Performance

| Item | Action |
|------|--------|
| Idempotency | X-Zammad-Delivery for dedup; Zammad retries up to 4× on failure |
| Rate limiting | Rate-limit POST /zammad/webhook (middleware or ingress) |
| MCP monitoring | Monitor MCP call volume; back off on Zammad API errors |

---

## 7. Testing Strategy

| Phase | Test scope |
|-------|------------|
| **Phase 1** | Unit tests: ZammadRequest schema validation; `_normalize_zammad_request` output (`target_agent_id`, `requires_routing`, `session_id`); Request Manager ZAMMAD branch creates ZammadRequest; agent-service passes `target_agent_id` to session manager; session manager creates specialist session when `requires_routing=False` |
| **Phase 2** | Integration: POST to `/zammad/webhook` with mock payload; verify signature rejection (invalid HMAC → 401); verify event_data shape and `send_request_event` called; verify idempotency (duplicate X-Zammad-Delivery → skip); verify feedback-loop (article from aiAgentUserId → skip); verify group allowlist; ZammadIntegrationHandler no-op returns success |
| **Phase 3** | E2E or manual: Inject Zammad-like CloudEvent → agent processes → verify MCP `zammad_add_article` called (or mock); chat widget: user sends message → reply appears |

---

## 8. Open Questions

| Question | Owner / Next Step |
|----------|-------------------|
| KB sync: static files only? | Per meeting notes: static files for now; no Zammad wiki |
| Escalation flow: trigger logic, state names, owner resolution | TBD; MCP supports it; flow details pending |
| Promptguards: Windows laptop approval authority | TBD per meeting notes |
| Zammad Time Event trigger for idle tickets | Later phase; Zammad trigger preferred over CronJob |

---

## 9. Risk Summary

| Risk | Mitigation |
|------|------------|
| Feedback loop (agent’s own articles) | Filter webhooks where article creator = AI agent’s Zammad user |
| Zammad MCP community-maintained | Review code; consider contributing; fallback: minimal MCP wrapper |
| Chat requires agent available | AI agent user + availability config; or “Leave a message” mode |
| Agent Service ignores target_agent_id | Phase 1: Pass to session manager; create specialist session when requires_routing=False (Section 2.2) |
| No ZAMMAD delivery handler | Phase 2: Add no-op ZammadIntegrationHandler to prevent `ValueError` when ZAMMAD in delivery configs |

---

## 10. Related Documents

- [Meeting Notes: Agent Capabilities](MEETING_NOTES_AGENT_CAPABILITIES_AND_WORKFLOW.md) — Meeting outcomes
- [Zammad Ticketing Channel Plan](ZAMMAD_TICKETING_CHANNEL_PLAN.md) — Technical reference (payloads, MCP tools)
