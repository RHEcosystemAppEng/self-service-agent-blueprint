# Channel behavior

Reference for per-channel conversation semantics: policy fields, resolution, snapshots, delivery binding, and how to add a new `IntegrationType`.

**Code-first:** Channel policy is defined in **`shared_models/channel_registry.py`** (`CHANNEL_REGISTRY`). Session snapshots store policy on the row; DB `integration_default_configs` holds delivery config only.

## Find what you need

| I want to… | Start here |
|------------|------------|
| Add or wire a new channel | [Adding a channel](#adding-a-channel) |
| Configure pooling (Slack vs web, solo vs unified) | [Operator configuration](#operator-configuration) |
| Understand ticket vs web/`ticket_id` in metadata | [Cross-channel pitfalls](#cross-channel-pitfalls) |
| Debug session reuse, pins, or scope | [Session and delivery semantics](#session-and-delivery-semantics) |
| Override policy without a release (advanced) | [DB policy override (ops)](#db-policy-override-ops) |
| Trace code or env vars | [Runtime reference](#runtime-reference) |

## Concepts (three layers)

| Layer | Where | Purpose |
|-------|--------|---------|
| **Ingress / normalizer** | `NormalizedRequest.integration_context` | Per-request shape (ticket id, Slack channel, `platform`, etc.) |
| **Channel behavior** | `CHANNEL_REGISTRY` → snapshot on `RequestSession.integration_metadata._channel_behavior` | Session scope, entry agent, return-to-router, delivery binding |
| **Delivery defaults** | Same DB row, other `config` keys | How replies are rendered (Slack threading, email, ticket-system REST, etc.) |

Do not put delivery UX or secrets into `channel_behavior`.

## Policy fields

Resolved at session create from the registry (+ optional overrides), then stored as `_channel_behavior` on the session row. Runtime reads the **snapshot**, not live registry edits.

| Field | Meaning |
|-------|---------|
| `entry_agent_id` | First agent on new sessions; `null` → `DEFAULT_AGENT_ID`. Must be on `AGENT_ID_ALLOWLIST` when set. |
| `allow_return_to_router` | If `false`, specialists do not auto-return to router |
| `session_scope` | How RM picks or creates a session — [Session scope](#session-scope) |
| `exclude_from_unified_session_pool` | If `true`, unified-session lookup must not reuse this channel’s rows |
| `delivery_binding` | `STANDARD` vs `TICKET_THREAD` — [Delivery binding](#delivery-binding) |
| `session_isolated_by_integration_type` | If `true`, solo session pool for this type only (without global `SESSION_PER_INTEGRATION_TYPE`) |

Other fields exist on `ChannelBehaviorPolicy` but are not knobs today: `schema_version` (defaults to `1`, not validated) and `router_agent_id` (v1 always resolves to `DEFAULT_AGENT_ID`).

**Typical routing:** web/CLI leave `entry_agent_id` unset and set `allow_return_to_router: true`. Ticket channels use `entry_agent_id: ticket-review-agent` and `allow_return_to_router: false`.

## Operator configuration

End users cannot set channel behavior. There is no admin REST API for policy JSON.

| Goal | Where to set it |
|------|-----------------|
| Global router / default entry | Helm `agent.defaultAgentId` → `DEFAULT_AGENT_ID` |
| Unified vs solo session pool (all `PER_USER` channels) | Helm `requestManagement.requestManager.sessions.perIntegrationType` → `SESSION_PER_INTEGRATION_TYPE` |
| Per-channel policy (e.g. isolate Slack from web) | **Preferred:** `requestManagement.requestManager.channelBehavior.overrides` |
| Product defaults for every install | `CHANNEL_REGISTRY` in code (release) |
| One-off / pilot without redeploy | DB `config.channel_behavior` + `allowDbOverride: true` — [DB policy override](#db-policy-override-ops) |

**Helm partial overrides** (request-manager): keys are `IntegrationType` names; values are partial `ChannelBehaviorPolicy` fields. Sets env `CHANNEL_BEHAVIOR_OVERRIDES` (JSON).

```yaml
requestManagement:
  requestManager:
    channelBehavior:
      allowDbOverride: false
      overrides:
        SLACK:
          session_isolated_by_integration_type: true
```

Merge order at session create: [Resolution and snapshots](#resolution-and-snapshots). Dispatcher `config` upsert refreshes delivery keys only and **preserves** existing `config.channel_behavior` in Postgres.

## `CHANNEL_REGISTRY`

`shared_models/channel_registry.py` maps each `IntegrationType` to a **`ChannelDefinition`**:

- **`behavior`** — `ChannelBehaviorPolicy`
- **`ticket_user_id_suffix`** — when true, RM suffixes canonical user id for MCP (Zammad today)

**Templates:** `_PER_USER_BEHAVIOR` (chat) and **`PER_TICKET_BEHAVIOR`** (ticket backends). Register with `_per_user(IntegrationType.X, ...)` or `ChannelDefinition(..., behavior=PER_TICKET_BEHAVIOR.model_copy(deep=True))`.

**Derived helpers** (prefer over hardcoded type lists):

- `per_ticket_integration_types()`, `ticket_delivery_integration_types()`, `ticket_delivery_eligible_types()` (registry `TICKET_THREAD` **and** wired dispatcher handler)
- `channel_uses_ticket_user_id_suffix()`, `registry_behavior_for()`, `get_channel_definition()`

**Deployment wiring:** `WIRED_RM_AND_DISPATCHER`, `WIRED_RM_INGRESS_ONLY`, `WIRED_DISPATCHER_ONLY` → unions `WIRED_REQUEST_MANAGER_INGRESS_TYPES` and `WIRED_DISPATCHER_HANDLER_TYPES`. A type can be in `CHANNEL_REGISTRY` only (e.g. SMS, TEAMS) until added to a `WIRED_*` set.

Unregistered enum values fail closed at `resolve_channel_behavior()`.

## Session and delivery semantics

### Session scope

Controls how Request Manager resolves `session_id` for the inbound `integration_type`.

| Value | How sessions are chosen |
|-------|-------------------------|
| `PER_USER` (default) | Reuse newest active session for user (and per `integration_type` when solo). New UUID if none. Subject to [pool exclusion](#pool-exclusion). Slack thread continuity: [session pin](#session-pin-metadatasession_id) or `thread_id` metadata. |
| `PER_TICKET` | Requires `ticket_id`. Stable id `{integration_type}-{ticket_id}` (e.g. `zammad-42`). Multiple active sessions per user+integration allowed (partial unique index excludes `PER_TICKET`). Ingress must be the ticket integration type — RM does not infer ticket scope from `ticket_id` on `WEB`/`CLI`. |

### Pool exclusion

`exclude_from_unified_session_pool: true` excludes rows from unified `PER_USER` lookup (`find_active_per_user_sessions` in Python; unified mode also excludes `session_scope=PER_TICKET` in SQL). Ticket policies set this with `PER_TICKET`. Rows without a `_channel_behavior` snapshot are excluded (logged) and must not be reused.

### Delivery binding

RM copies `delivery_binding` from the session snapshot into `integration_context` on forward — not from client metadata.

| Value | Behavior |
|-------|----------|
| `STANDARD` | Slack, email, webhooks, test handler, HTTP response path, etc. |
| `TICKET_THREAD` | Dispatcher keeps types in `ticket_delivery_eligible_types()`; smart defaults use `is_ticket_delivery_eligible()`. Requires `ticket_id` in delivery context. Customer-visible reply → ticket article via dispatcher handler. |

### Session pin and stable create id

| Mechanism | How it works |
|-----------|----------------|
| **Session pin** | `metadata.session_id` continues an existing row (`validate_explicit_session_pin` before pool / create). |
| **Stable id at create** | `SessionCreate.explicit_session_id` at insert; `PER_TICKET` uses `ticket_session_id()`. |

#### Session pin (`metadata.session_id`)

When present, RM skips unified pool and PER_TICKET create and validates:

1. Row exists for canonical user, `ACTIVE`, not expired
2. Inbound `integration_type` matches row (no cross-channel pin)
3. Row has `_channel_behavior` snapshot
4. Scope compatibility: ticket row only for `PER_TICKET` inbound; isolated rows not pin-able from unified `PER_USER` inbound

**Failure example:** `CLI` + `metadata.session_id: zammad-42` → **400** (integration type / scope mismatch). Use ticket ingress + `ticket_id` for ticket traffic.

#### Stable id at create (`explicit_session_id`)

Internal create path: fixed `session_id` instead of UUID. PER_TICKET sets `{type}-{ticket_id}`.

### Shared vs solo sessions

| Mode | Env | Session lookup |
|------|-----|----------------|
| **Unified pool** | `SESSION_PER_INTEGRATION_TYPE=false` | One active “general” session per user (ticket/isolated rows excluded) |
| **Solo per channel type** | `SESSION_PER_INTEGRATION_TYPE=true` | Separate active session per `integration_type` |

**Ticket channels** use `PER_TICKET` + `exclude_from_unified_session_pool: true` + `delivery_binding: TICKET_THREAD` regardless of that env. **`session_isolated_by_integration_type`** forces solo pool for one integration type only, without global `SESSION_PER_INTEGRATION_TYPE=true`.

## Resolution and snapshots

**Merge order** (request-manager session create):

1. `CHANNEL_REGISTRY`
2. `CHANNEL_BEHAVIOR_OVERRIDES` env (Helm `channelBehavior.overrides`)
3. DB `config.channel_behavior` when `CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE=true` and async DB session available
4. Fill null `entry_agent_id` / `router_agent_id` from `DEFAULT_AGENT_ID`
5. Allowlist validation — fail closed on invalid policy

`resolve_channel_behavior_sync()` runs steps 1, 2, 4–5 only (no DB). Agent-service uses it only when no request-manager `session_id`; normal turns read the session-row snapshot.

**Snapshot rules:**

- Written on every session create to `integration_metadata["_channel_behavior"]`
- Post-resolve shape: null agent ids from registry are stored as `DEFAULT_AGENT_ID`, not `null`
- Client `_channel_*` keys stripped before merge; server snapshot wins
- Policy changes apply to **new sessions** only
- Missing snapshot: rejected in agent-service; excluded from unified pool lookup

## Cross-channel pitfalls

**Naming:** Branch session/delivery logic on policy (`PER_TICKET`, `TICKET_THREAD`, …), not the string “Zammad”. Use concrete `IntegrationType` names on ingress, webhooks, and Helm only.

**`ticket_id` in metadata does not make a ticket channel.** Behavior comes from `resolve_channel_behavior(inbound_integration_type)`:

| Inbound | Typical policy | `metadata.ticket_id` |
|---------|----------------|----------------------|
| `WEB` / `SLACK` | `PER_USER`, `STANDARD` | Optional agent context; **does not** open `zammad-{id}` |
| `ZAMMAD` | `PER_TICKET`, `TICKET_THREAD` | **Required**; session `zammad-{ticket_id}` |

Delivery `delivery_binding` comes from the **session snapshot**, not from whether the client sent `ticket_id`. Unusual policies (e.g. `PER_TICKET` on `WEB`) need [DB override](#db-policy-override-ops).

## DB policy override (ops)

**Default:** `CHANNEL_REGISTRY` + optional Helm overrides. Baseline policy is not in `integration_default_configs.config` (delivery bootstrap only). DB `channel_behavior` is read only when `allowDbOverride` is enabled.

Use for cluster-specific choices without a release — commonly **isolating Slack from the web unified pool**. Prefer Helm `channelBehavior.overrides` when possible; use DB for one-off pilots.

| Goal | Lever |
|------|--------|
| Slack not sharing sessions with web | `session_isolated_by_integration_type: true` on `SLACK` |
| Every channel type solo (not just Slack) | `SESSION_PER_INTEGRATION_TYPE=true` (global env) |
| Different first agent / no auto-return | `entry_agent_id`, `allow_return_to_router` |
| Slack as ticket thread | **Wrong** — use Zammad (or ticket) ingress with `ticket_id` |

### How to enable

1. `allowDbOverride: true` under `requestManagement.requestManager.channelBehavior` (or `CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE=true` on request-manager)
2. Restart request-manager pods (agent-service uses snapshots from create time)
3. Partial `channel_behavior` JSON under `integration_default_configs.config` via SQL; `null` values ignored; any `ChannelBehaviorPolicy` field allowed

```sql
UPDATE integration_default_configs
SET config = jsonb_set(
  COALESCE(config, '{}'::jsonb),
  '{channel_behavior}',
  '{"session_isolated_by_integration_type": true}'::jsonb,
  true
)
WHERE integration_type = 'SLACK';
```

Existing active sessions keep their snapshot until expiry or replacement. Keep `CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE=false` unless you need this path.

| Constraint | Behavior |
|------------|----------|
| New sessions only | Override at session create; existing rows unchanged |
| Dispatcher upsert | Preserves DB `channel_behavior`; does not write policy from code |
| Validation | Agent ids on allowlist; invalid policy fails session create |
| Disable | Set env `false`; DB JSON ignored but can remain |

## Runtime reference

**Delivery path:** `_forward_response_to_integration_dispatcher` merges `delivery_binding` from the session snapshot (`delivery_context_for_forward`). Dispatcher `main.py` filters via `filter_configs_for_delivery_binding`; smart defaults gate ticket delivery with `is_ticket_delivery_eligible()`.

**Who writes what:**

| Writer | Owns |
|--------|------|
| `channel_registry.py` | Policy per `IntegrationType` |
| Session row snapshot | `_channel_behavior` at create (runtime truth) |
| Integration-dispatcher upsert | Delivery keys only |

**Key modules:** `channel_registry.py`, `channel_policy_types.py`, `channel_behavior.py` (resolver), `channel_behavior_session.py` (pin, pool, ticket session), `communication_strategy.py` / `session_events.py` (RM create), `session_manager.py` (agent-service snapshot), `integration-dispatcher/.../main.py` (delivery filter).

**Environment variables:**

| Variable | Effect |
|----------|--------|
| `DEFAULT_AGENT_ID` | Global router; fills null entry ids in policy |
| `SESSION_PER_INTEGRATION_TYPE` | Unified vs solo session pool |
| `CHANNEL_BEHAVIOR_OVERRIDES` | JSON partial policy from Helm |
| `CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE` | Merge DB `channel_behavior` after env |
| `AGENT_ID_ALLOWLIST` | Optional; unset uses built-in agent ids |

**Known limits:** No per-thread `session_scope` (use pin / `thread_id`). `TICKET_THREAD` requires wired handler + eligible type. Rows without snapshot fail closed. Policy edits apply to new sessions only.

---

## Adding a channel

Checklist for a new `IntegrationType`.

### 1. Python type + registry

- [ ] Add value to `IntegrationType` in `shared-models/src/shared_models/models.py`
- [ ] Register in `channel_registry.py` `_build_registry()` (unregistered types fail closed)
- [ ] Policy shape: copy `_PER_USER_BEHAVIOR` or `PER_TICKET_BEHAVIOR` — see `channel_registry.py` and `PER_TICKET_CHANNEL_BEHAVIOR_SEED` for ticket JSON used in tests
- [ ] Do not seed `channel_behavior` in DB or dispatcher upsert

**PER_USER:**

```python
IntegrationType.YOUR_TYPE: _per_user(IntegrationType.YOUR_TYPE),
# Optional: _per_user(IntegrationType.SLACK, session_isolated_by_integration_type=True)
```

**Ticket backend:**

```python
registry[IntegrationType.YOUR_TYPE] = ChannelDefinition(
    integration_type=IntegrationType.YOUR_TYPE,
    behavior=PER_TICKET_BEHAVIOR.model_copy(deep=True),
    ticket_user_id_suffix=True,  # if RM should suffix canonical user id
)
```

### 2. Ingress (request-manager)

- [ ] Request schema in `request-manager/src/request_manager/schemas.py`
- [ ] Route / webhook handler
- [ ] Add to **`WIRED_RM_AND_DISPATCHER`** or **`WIRED_RM_INGRESS_ONLY`** (sync with RM routes)
- [ ] Normalizer: set `integration_context` contract; do **not** set `_channel_behavior` from clients

### 3. Session behavior

- [ ] `create_or_get_session_shared` / `session_events` usually need no change if policy-driven
- [ ] `PER_TICKET`: require `ticket_id`; stable id via `ticket_session_id(integration_type, ticket_id)`
- [ ] Tests: no cross-attach to ticket sessions; pin rejected on scope mismatch

### 4. Agent-service

- [ ] Usually none if registry covers entry agent and return-to-router
- [ ] Ticket UX (title merge): only if `session_scope == PER_TICKET`

### 5. Delivery (integration-dispatcher)

- [ ] Handler under `integration-dispatcher/.../integrations/`
- [ ] Add to **`WIRED_RM_AND_DISPATCHER`** or **`WIRED_DISPATCHER_ONLY`** (sync with `IntegrationDispatcher.handlers`)
- [ ] Entry in `IntegrationDefaultsService.default_integrations` (delivery `config` only)
- [ ] `TICKET_THREAD`: wire handler so `is_ticket_delivery_eligible()` is true

### 6. Request Manager forwarder

- [ ] Automatic when `session_id` present and snapshot exists

### 7. Helm / secrets

- [ ] Secrets per [AUTHENTICATION_GUIDE.md](../guides/AUTHENTICATION_GUIDE.md) — not in `channel_behavior`

### 8. Tests

- [ ] `test_channel_registry.py`, `test_channel_registry_wired.py`
- [ ] `test_wired_handlers_match_registry` / `test_wired_ingress_match_registry`
- [ ] Session behavior tests in request-manager and shared-models as needed

### 9. Agents

- [ ] New entry agent: `config/agents/<id>.yaml` and allowlist / `AGENT_ID_ALLOWLIST`
