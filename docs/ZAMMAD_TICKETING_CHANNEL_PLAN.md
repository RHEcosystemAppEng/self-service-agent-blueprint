# Zammad Ticketing Channel Integration Plan

**Status**: Planning  
**Related**: [ai-quickstart-contrib #18](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/18) — speeding up ticket resolution time  
**Last updated**: 2025-03-09

**Implementation touchpoints:** See [Ticketing Channel Game Plan](TICKETING_CHANNEL_GAMEPLAN.md) for codebase locations and required changes.

---

## Executive Summary

Add **Zammad** as the primary ticketing-native channel to the self-service agent blueprint. Zammad is **free and open source** (AGPL v3, no license fee). Tickets and articles = support cases; the agent uses the community [Zammad-MCP](https://github.com/basher83/Zammad-MCP) for ticket actions. **Leverage the built-in chat widget**: when a user sends a message via the chat, Zammad creates a ticket with articles; our agent replies via MCP (add article); the reply appears in the chat UI in real time — no standalone chat UI needed.

User posts via chat, email, or web form → webhook triggers agent → agent replies via MCP → user sees response in chat or ticket view. Multi-turn conversation lives in the ticket article thread.

---

## Why Zammad as Primary Ticketing-Native Option?

| Criterion | Zammad | Znuny | Gitea |
|-----------|--------|-------|-------|
| **Purpose-built ticketing** | Yes (helpdesk) | Yes (OTRS fork) | No (git issues) |
| **Free / open source** | Yes (AGPL) | Yes (GPL) | Yes |
| **Self-hosted** | Yes | Yes | Yes |
| **Built-in chat widget** | **Yes** — real-time UI | No | No |
| **Webhooks** | Triggers, X-Hub-Signature, retries | Web Service Notification | Gitea webhooks |
| **Helm chart** | Official (zammad-helm) | Community | Official |
| **MCP server** | Community ([Zammad-MCP](https://github.com/basher83/Zammad-MCP)) | Community (znuny_mcp) | Official (gitea-mcp) |
| **Stack complexity** | Elasticsearch (optional) | Lighter | Lightest |

Zammad’s built-in chat widget suits our needs: chat messages become ticket articles; our agent’s replies (added via MCP/REST API) appear in the chat in real time. No need to build a custom chat UI.

---

## Incoming vs Outgoing

| Direction | Mechanism | Who initiates | Notes |
|-----------|-----------|---------------|-------|
| **Incoming** (Zammad → blueprint) | Zammad triggers (webhooks) | Zammad POSTs to our endpoint on ticket/article create | New `POST /zammad/webhook` route. Configure trigger in Zammad Admin. |
| **Outgoing** (blueprint → Zammad) | Agent uses Zammad MCP | Agent calls `zammad_add_article`, `zammad_get_ticket`, etc. | MCP server calls Zammad REST API; no ZammadIntegrationHandler |

**Why MCP for outgoing:** Agent can add articles, update status, assign, search tickets — not just post a single reply. Single integration surface (MCP) for read + write.

---

## Interaction Model: Ticket Articles + Chat Widget

- **Chat flow**: User opens chat widget (embedded on site) → sends message → Zammad creates ticket with article → webhook fires → agent processes → agent adds article via MCP → **reply appears in chat UI** (chat is backed by ticket articles)
- **Email / web form flow**: Same pattern — ticket created → webhook → agent replies via MCP → user sees reply in ticket view or via email notification
- Full conversation in ticket article thread; session continuity via `ticket_id`

### Delivery Path: Chat Widget Responses via MCP

**Agent responses to the Zammad chat widget are delivered exclusively via MCP.** There is no Integration Dispatcher delivery handler for Zammad. The flow:

1. User sends message in chat widget → Zammad creates ticket article → webhook → agent processes
2. Agent calls `zammad_add_article` via Zammad MCP
3. MCP server posts to Zammad REST API → ticket article created
4. Chat widget displays the new article (chat is a view of ticket articles)

This differs from Slack/Email, where responses go through the Integration Dispatcher delivery pipeline and handlers post to each configured channel. For Zammad, the agent performs delivery directly via MCP; no `ZammadIntegrationHandler` exists.

**Chat widget behavior:** Zammad shows the chat only when at least one agent is available. To support an AI-first flow, create a dedicated Zammad agent user for the AI and keep it “available” (or use triggers to auto-assign chat sessions). The AI agent responds via MCP; its articles appear in the chat. Alternatively, configure “Leave a message” mode if chat should work when no human is online — messages become tickets; our agent processes asynchronously.

---

## Knowledge Base & RAG

**No built-in wiki in Zammad.** KB comes from the quickstart’s existing pipeline:

- `config/knowledge_bases/ticket-resolution/` — .txt files
- LlamaStack vector store → RAG
- Agent references via `knowledge_bases: ["ticket-resolution"]`

No sync from Zammad; KB is managed as static files or via ingestion pipeline. Simpler than Gitea’s wiki options.

---

## Agent Resolution Logic (Desired Behavior)

**Ideally**, the ticket-resolution agent should (per [issue #18](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/18)):

1. **Ask clarifying questions** — Multi-turn conversation allows the agent to request more detail (e.g. "What error message do you see?", "Which version are you on?") before suggesting a fix.
2. **Collect additional data** — Agent can ask for logs, screenshots, or reproduction steps. Zammad-MCP supports attachments (`zammad_get_article_attachments`, `zammad_download_attachment`).
3. **Recommend fixes from KB** — Use RAG over `knowledge_bases: ["ticket-resolution"]` to find solutions, SOPs, and known resolutions. Reply with recommended fixes, steps, or links to relevant docs.
4. **Match existing issues** — Search for similar open/resolved tickets (via `zammad_search_tickets`) and reference them when applicable.
5. **Confirm / update ticket status** — Use `zammad_update_ticket` to change state, priority, assignee.
6. **Close resolved tickets** — Agent asks "Has this resolved your issue?"; if yes, update ticket state to closed/resolved with success tag.
7. **Escalate to human** — When no KB or similar ticket helps, add escalation article and assign to support (see [Escalation Flow](#escalation-flow)).
8. **Create new ticket only when needed** — If no KB solution and no existing ticket covers the problem, create a new ticket via `zammad_create_ticket`.

**Flow:** User describes issue → agent queries KB + searches tickets → if solution found, reply with fix (optionally close when resolved) → if not, create new ticket and add summary article.

**Bypass case:** If a user creates a ticket directly (email, web form, Zammad UI) without going through the chat agent first, the webhook still fires. The agent should treat the incoming ticket the same way: query KB and search similar tickets. If it finds existing resolutions, add an article to the ticket with the recommended fix. The agent can attempt to resolve these tickets proactively by commenting with solutions when they exist in the KB.

**Safeguards:** Use KB content and input/output shields (Llama Guard) for compliance and accuracy. Add promptguards for controlled scenarios requiring policy checks or approvals (e.g., Windows laptop request — approval authority TBD: manager vs IT manager per request tier).

---

## Escalation Flow

**MCP actions (Zammad-MCP):**

| Action | MCP tool | Purpose |
|--------|----------|---------|
| Add escalation article | `zammad_add_article` | "Escalating — [summary]. Recommended fix: [X]." |
| Update ticket | `zammad_update_ticket` | Assign, change state, priority |
| Assign to human | `zammad_update_ticket` (owner) | Assign to support agent |

**Flow TBD:** Trigger logic (when to escalate), state names, owner resolution.

---

## Implementation Phases

### Phase 1: Zammad MCP + Agent Config (Foundation)

**Goal**: Agent can read/update Zammad tickets via MCP.

| Task | Details |
|------|---------|
| Deploy Zammad MCP | Use [Zammad-MCP](https://github.com/basher83/Zammad-MCP) (AGPL-3.0). Deploy via Docker (`ghcr.io/basher83/zammad-mcp`) or uvx. Requires `ZAMMAD_URL` (include `/api/v1`), `ZAMMAD_HTTP_TOKEN`. Supports stdio and HTTP transports. |
| Helm integration | Add Zammad MCP deployment; config similar to Snow MCP (`mcp_servers` in agent YAML). |
| Agent config | Add Zammad MCP to ticketing/resolution agent; expose `zammad_get_ticket`, `zammad_add_article`, `zammad_search_tickets`, `zammad_update_ticket`, etc. |
| Ticketing agent | New agent (e.g. `ticket-resolution-agent`) with Zammad MCP + `knowledge_bases: ["ticket-resolution"]`. Input/output shields (Llama Guard). |

**Deliverables**: Agent can create tickets, add articles, search tickets via MCP.

---

### Phase 2: Zammad Webhook → Request Manager (Incoming Channel)

**Goal**: Ticket/article events trigger agent processing.

| Task | Details |
|------|---------|
| IntegrationType | Add `ZAMMAD` to `IntegrationType` enum in shared-models. |
| Zammad webhook handler | **New** route `POST /zammad/webhook`. Zammad triggers POST to our endpoint. Verify `X-Hub-Signature` (HMAC-SHA1) with trigger secret. **Filter:** ignore events where article creator is the agent’s Zammad user (prevent feedback loop). Group allowlist: only process configured groups. |
| Event mapping | Map ticket create / article create (customer/external) → CloudEvent `request.created`. Skip internal notes, agent articles. Use `X-Zammad-Delivery` for deduplication. |
| Request schema | `ZammadRequest` in `request-manager/.../schemas.py` with `ticket_id`, `article_id`, `group_id`, `group_name`, `owner_id`, `created_by_id`, `zammad_delivery_id`. |
| Normalizer | Add `_normalize_zammad_request` in `request-manager/.../normalizer.py`; set `target_agent_id="ticket-resolution-agent"`, `requires_routing=False`; pass ticket metadata in `integration_context`. Session ID: `zammad-{ticket_id}`. |
| Request Manager | Add `elif integration_type == IntegrationType.ZAMMAD:` branch; create `ZammadRequest`. |
| Response delivery | **None.** Agent delivers via MCP; no ZammadIntegrationHandler. |

**Deliverables**: New ticket or customer article triggers agent; agent replies via MCP; reply appears in chat or ticket view.

---

### Phase 3: Chat Widget Integration (Leverage Built-in UI)

**Goal**: Ensure chat widget is usable for AI-assisted support.

| Task | Details |
|------|---------|
| AI agent user | Create Zammad user for AI agent; assign Agent role. |
| Agent availability | Keep AI agent “available” (or use triggers to auto-assign) so chat widget is visible. Alternatively, use “Leave a message” mode. |
| Chat widget config | Configure chat in Zammad Admin (Channels → Chat). Embed widget script on target site. |
| Validation | User sends chat message → webhook → agent replies via MCP → reply appears in chat. |

**Deliverables**: Chat widget provides real-time UI; AI replies visible in chat. No custom chat UI needed.

---

### Phase 4: Demo Pre-population (Deployment / Demo)

**Goal**: Seed Zammad with sample data at quickstart boot.

| Task | Details |
|------|---------|
| Zammad deployment | Add Zammad as optional component; `make deploy-zammad` or similar. |
| Init / seed | Create sample groups, sample tickets. No GH sync (Zammad is not git-based). |
| Helm integration | Zammad ticketing ties into `make helm-install-test`, `helm/values.yaml`. Zammad, Zammad MCP as conditional blocks (`zammad.enabled`). |

---

## Future / v2

Per [issue #18](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/18):

| Feature | Description |
|---------|-------------|
| **Docling for PDFs** | Extract information from PDFs (attachments, KB docs) into the knowledge base. |
| **Multi-model for images** | Analyze screenshots attached to tickets (e.g. error dialogs, UI issues) with vision-capable models. |
| **Optional resolved-ticket creation** | When the agent resolves via chat, create a summarized "resolved" ticket for audit (per Pete Davis comment in issue #18). |
| **Zammad AI Provider integration** | Optional: Point Zammad's built-in AI (Ticket Summary, Writing Assistant, AI Agents) at LlamaStack via Custom/OpenAI-compatible provider. For human agents using Zammad UI; separate from our webhook+MCP agent. See [Zammad AI Provider docs](https://admin-docs.zammad.org/en/pre-release/ai/provider.html). |
| **Proactive work on idle tickets** | Zammad Time Event trigger (e.g., "Ticket Pending Time Reached") fires webhook when ticket idle; agent adds suggested resolution via MCP. Preferred over CronJob — reuses webhook, no extra infra. |

Out of scope for v1.

---

## Deployment & Helm Integration

**Assumption:** Zammad ticketing integrates with the existing Helm install mechanism.

| Existing mechanism | Zammad ticketing fit |
|--------------------|----------------------|
| `make helm-install-test` / `helm-install-prod` | Add `zammad.enabled`, `zammad.mcp.enabled` flags |
| `helm/values.yaml` | Add `zammad` block (url, webhookSecret, defaultGroup, mcp.uri) |
| `make deploy-email-server` | Pattern for `make deploy-zammad` (optional Zammad instance) |
| Init job | Optional: create AI agent user, sample groups |

**Zammad official Helm chart:** [zammad/zammad-helm](https://github.com/zammad/zammad-helm) — use as subchart or dependency.

---

## Technical Details

### Zammad Webhook Payload (Relevant Fields)

```json
{
  "ticket": {
    "id": 81,
    "number": "10081",
    "title": "...",
    "state": "open",
    "group_id": 3,
    "owner_id": 5,
    "article_ids": [104],
    "created_by_id": 3,
    "customer_id": 8
  },
  "article": {
    "id": 104,
    "ticket_id": 81,
    "body": "User's message...",
    "sender": "Customer",
    "sender_id": 2,
    "internal": false,
    "origin_by_id": 8
  }
}
```

### Zammad Webhook Headers

- `X-Zammad-Trigger`: Trigger name
- `X-Zammad-Delivery`: Unique ID (deduplication)
- `X-Hub-Signature`: HMAC-SHA1 (if configured)

### Zammad MCP Tools (basher83/Zammad-MCP)

- **Ticket:** `zammad_search_tickets`, `zammad_get_ticket`, `zammad_create_ticket`, `zammad_update_ticket`, `zammad_add_article`, `zammad_add_ticket_tag`, `zammad_remove_ticket_tag`
- **Attachments:** `zammad_get_article_attachments`, `zammad_download_attachment`, `zammad_delete_attachment`
- **Users & orgs:** `zammad_get_user`, `zammad_search_users`, `zammad_get_organization`, `zammad_search_organizations`, `zammad_get_current_user`
- **System:** `zammad_list_groups`, `zammad_list_ticket_states`, `zammad_list_ticket_priorities`, `zammad_get_ticket_stats`

### Database / Schema Changes

- `IntegrationType`: add `ZAMMAD`
- Alembic migration for enum
- `ZammadRequest` schema

### Configuration

```yaml
# Helm values
zammad:
  enabled: true
  url: "https://zammad.example.com"        # Zammad-MCP needs url + /api/v1
  webhookSecret: "<trigger-secret>"
  defaultGroup: "Support"
  mcp:
    enabled: true
    uri: "http://zammad-mcp:8000/mcp"       # HTTP transport (MCP_TRANSPORT=http)
    # Env: ZAMMAD_URL, ZAMMAD_HTTP_TOKEN
  chat:
    enabled: true  # Use built-in chat widget
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Zammad instance | Self-hosted; Docker or Helm |
| Zammad MCP server | [Zammad-MCP](https://github.com/basher83/Zammad-MCP) — community; holds Zammad API token |
| Zammad trigger | Configured in Zammad Admin for webhook POST |
| Request Manager | Add `ZammadRequest` handling |
| Integration Dispatcher | Add `POST /zammad/webhook` route |
| Agent Service | Add Zammad MCP config |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Zammad MCP community-maintained | Review codebase; consider contributing. Fallback: minimal MCP wrapper around Zammad REST API. |
| Feedback loop | Filter webhooks where article creator is AI agent’s Zammad user. |
| Chat requires agent available | Create AI agent user; keep available or use “Leave a message” mode. |
| Elasticsearch (optional) | Zammad can run without ES for smaller deployments. |

---

## Audit: Gaps, Security, Performance

### Critical Gaps

| Gap | Mitigation |
|-----|------------|
| **Feedback loop** | Ignore webhooks where `article.created_by_id` matches AI agent’s Zammad user. |
| **Request Manager** | Add ZAMMAD branch. |
| **Session ID** | `zammad-{ticket_id}`. |
| **Event filtering** | Only process ticket create + article create (customer/external). Skip internal notes, agent articles. |

### Security

| Item | Recommendation |
|------|----------------|
| **Webhook signature** | Verify `X-Hub-Signature` (HMAC-SHA1) with trigger secret. |
| **Group allowlist** | Only process configured groups. |
| **MCP token** | Store in K8s Secret; never log. |
| **Rate limiting** | Rate-limit webhook endpoint. |
| **Safety shields** | Input/output shields on ticket-resolution agent. |

### Performance

| Item | Recommendation |
|------|----------------|
| **MCP call volume** | Agent may make multiple ticket/article calls. Monitor; back off on errors. |
| **Webhook retries** | Zammad retries up to 4 times on failure. Handle idempotently via `X-Zammad-Delivery`. |
| **Deduplication** | Use `X-Zammad-Delivery` for idempotency. |

---

## Success Criteria

- [ ] Agent can read and update Zammad tickets via MCP
- [ ] New ticket or customer article triggers agent processing (Zammad webhook → Integration Dispatcher)
- [ ] Agent reply is posted as ticket article via MCP
- [ ] No feedback loop (agent’s own articles ignored)
- [ ] Multi-turn conversation works (user article → agent article → repeat)
- [ ] **Chat widget:** User sends message → agent reply appears in chat UI
- [ ] Session continuity via `ticket_id`
- [ ] Documented in README / quickstart guide

---

## Gitea vs Zammad vs Znuny: When to Choose Which?

| Choose Gitea when | Choose Zammad when | Choose Znuny when |
|-------------------|--------------------|-------------------|
| Aligning with ai-quickstart-contrib #18 | Need purpose-built ticketing + **chat UI** | Need ITSM (queues, CMDB, time accounting) |
| Want wiki-as-KB in same platform | Free, modern helpdesk, simpler webhooks | Heavier OTRS-style workflows |
| Git-centric workflow | Official Helm, chat widget, good MCP | Community MCP, Web Service config |

---

## References

- [ai-quickstart-contrib #18](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/18)
- [Zammad-MCP](https://github.com/basher83/Zammad-MCP) — Zammad MCP server (tickets, attachments, users, orgs, prompts)
- [Zammad documentation](https://docs.zammad.org/)
- [Zammad Webhooks](https://admin-docs.zammad.org/en/3.x/manage/trigger/webhooks.html)
- [Zammad Chat](https://admin-docs.zammad.org/en/4.x/channels/chat.html)
- [zammad/zammad-helm](https://github.com/zammad/zammad-helm) — Official Helm chart
- [Ticketing Channel Game Plan](TICKETING_CHANNEL_GAMEPLAN.md) — Implementation touchpoints
- Blueprint: `guides/INTEGRATION_GUIDE.md`, `docs/ARCHITECTURE_DIAGRAMS.md`
