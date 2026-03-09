Meeting Notes: IT Self-Service Agent Extension — Ticketing Channel

Date: March 10, 2025
Meeting: Continue to discuss / define extension to IT self-service agent
Topic: Ticketing channel — agent capabilities, workflow, safeguards


1. Agent Capabilities and Workflow (From Discussion)

Login and conversation management
   • Users should be able to start new conversations/tickets or continue existing ones

Point to existing content before opening new tickets
   • When docs or open tickets address the query, point users there rather than open a new ticket

Autonomous resolution (A to Z)
   • Some scenarios should be resolvable end-to-end without human interaction (e.g., "What's the printer?")
   • Agent asks "Has this resolved your issue?" — if yes, close ticket

Safeguards
   • Safeguards from knowledge base or shields (LlamaStack)
   • Promptguards for certain scenarios (LlamaStack) — e.g., gate Windows laptop request

Escalation
   • Mechanism to ask for human intervention; ticket escalation when needed
   • Zammad MCP supports this (zammad_add_article for escalation note, zammad_update_ticket to assign/change state)

Agent on existing tickets (later phase)
   • How can the agent solve or comment on existing tickets? Jobs vs direct API?
   • Goal: reduce duration of tickets
   • Agent always uses MCP. Chat is the user view of ticket articles; agent posts via zammad_add_article. For user-initiated (user adds article → webhook → agent replies via MCP). For proactive work on idle tickets: a scheduled or trigger-based job invokes the agent → agent uses MCP to add articles. Zammad trigger preferred — Zammad has Time Event activators (e.g., "Ticket Pending Time Reached") designed for this; reuses our webhook; no CronJob to maintain.


2. Knowledge Base (KB)

   • Only docs loaded into vector db for now
   • Zammad has no wiki; use quickstart pipeline (static files, RAG)
   • KBs managed as static files; no sync from Zammad


3. Zammad Deployment (High Level)

   • Phase 1: Deploy Zammad instance first
   • Phase 2: Deploy MCP, wire to agent, add ticket-resolution-agent config
   • Phase 3: Add webhook route, extend IntegrationType, add schemas and normalizer. Session ID = zammad-{ticket_id}
   • Phase 4: Chat widget setup (AI agent user, availability)
   • Phase 5: Helm integration, demo seed data

   Optional later phase: Zammad Time Event trigger for proactive work on idle tickets (e.g., "Ticket Pending Time Reached" fires webhook → agent adds suggested resolution via MCP).

   Flow: webhook → Integration Dispatcher → broker → Request Manager → Agent → MCP. Agent uses MCP only; replies go directly via MCP.

   Feedback loop: Filter webhooks where article creator = our AI agent user. Don't process our own replies.
