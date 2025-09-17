"""Agent routing detection and validation logic."""

import os
from typing import Optional

import structlog
from shared_db import AgentMapping, create_agent_mapping

logger = structlog.get_logger()


async def _get_available_agents() -> AgentMapping:
    """Get available agents from the agent service."""
    import httpx

    try:
        # Get agent service URL from environment
        agent_service_url = os.getenv(
            "AGENT_SERVICE_URL", "http://self-service-agent-agent-service:80"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{agent_service_url}/agents", timeout=10.0)
            response.raise_for_status()

            data = response.json()
            agents = data.get("agents", {})

            # Create type-safe agent mapping
            agent_mapping = create_agent_mapping(agents)

            logger.info(
                "Retrieved available agents from agent-service",
                count=len(agents),
                agents=list(agents.keys()),
            )

            return agent_mapping

    except Exception as e:
        logger.error("Failed to get available agents", error=str(e))
        # Return empty mapping if we can't get the real one
        # This will cause routing detection to fail gracefully
        logger.warning(
            "Failed to get available agents, routing detection may not work properly"
        )
        return create_agent_mapping({})


async def detect_and_validate_agent_routing(
    content: str,
    current_agent_id: str,
    available_agents: Optional[AgentMapping] = None,
) -> Optional[str]:
    """Detect routing signals in agent responses.

    Supports two routing signals (matching session-manager approach):
    1. task_complete_return_to_router - routes back to routing agent (from any agent)
    2. Direct agent name - routes to specific agent (from routing agent)
    """

    # Get available agents if not provided
    if available_agents is None:
        available_agents = await _get_available_agents()

    agent_response = content.strip()
    signal = agent_response.lower()

    # Check for task completion signal first (from any agent)
    if signal == "task_complete_return_to_router":
        logger.info(
            "Task completion signal detected - routing back to router",
            current_agent_id=current_agent_id,
            response=agent_response,
        )
        # Use the default agent ID from environment (same as agent service)
        default_agent = os.getenv("DEFAULT_AGENT_ID", "routing-agent")
        return default_agent

    # Check for direct agent name routing (case-insensitive)
    # This matches the session-manager approach: signal in self.agents
    for agent_name in available_agents.get_all_names():
        if signal == agent_name.lower():
            # Don't route to the same agent we're already on
            if (
                agent_name.lower()
                != os.getenv("DEFAULT_AGENT_ID", "routing-agent").lower()
            ):
                target_uuid = available_agents.get_uuid(agent_name)
                logger.info(
                    "Direct agent routing detected",
                    routing_response=agent_response,
                    target_agent_name=agent_name,
                    target_agent_uuid=target_uuid,
                    current_agent_id=current_agent_id,
                )
                return agent_name
            else:
                logger.debug(
                    "Ignoring routing to same agent",
                    routing_response=agent_response,
                    target_agent=agent_name,
                    current_agent_id=current_agent_id,
                )

    logger.debug(
        "No valid routing signal detected - ignoring",
        routing_response=agent_response,
        available_agents=available_agents.get_all_names(),
        current_agent_id=current_agent_id,
    )

    return None
