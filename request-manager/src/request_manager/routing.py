"""Agent routing detection and validation logic."""

import os
from typing import Dict, Optional

import structlog

logger = structlog.get_logger()


async def _get_available_agents() -> Dict[str, str]:
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
            agents = data.get("agents", [])

            # Convert list to dict (agent_name -> agent_uuid)
            # For now, we'll use the agent names as both key and value
            # In a real implementation, you'd get the actual UUIDs
            agent_mapping = {agent: agent for agent in agents}

            logger.info(
                "Retrieved available agents from agent-service",
                count=len(agents),
                agents=agents,
            )

            return agent_mapping

    except Exception as e:
        logger.error("Failed to get available agents", error=str(e))
        # Return default mapping if we can't get the real one
        return {"routing-agent": "routing-agent", "laptop-refresh": "laptop-refresh"}


async def detect_and_validate_agent_routing(
    content: str,
    current_agent_id: str,
    available_agents: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Detect routing signals in agent responses.

    Supports two routing signals:
    1. task_complete_return_to_router - routes back to routing agent (from any agent)
    2. ROUTE_TO: [agent-name] - routes to specific agent (from routing agent)
    """

    # Get available agents if not provided
    if available_agents is None:
        available_agents = await _get_available_agents()

    agent_response = content.strip()

    # Check for task completion signal first (from any agent)
    if "task_complete_return_to_router" in agent_response:
        logger.info(
            "Task completion signal detected - routing back to router",
            current_agent_id=current_agent_id,
            response=agent_response,
        )
        # Use the default agent ID from environment (same as agent service)
        default_agent = os.getenv("DEFAULT_AGENT_ID", "routing-agent")
        return default_agent

    # Check for structured routing response (ROUTE_TO: agent-name)
    # Look for ROUTE_TO: anywhere in the response, not just at the start
    if "ROUTE_TO:" in agent_response:
        # Extract the target agent from the ROUTE_TO: line
        lines = agent_response.split("\n")
        for line in lines:
            if line.strip().startswith("ROUTE_TO:"):
                target_agent = line.split(":", 1)[1].strip()
                if target_agent in available_agents:
                    logger.info(
                        "Structured routing detected",
                        routing_response=agent_response,
                        target_agent_name=target_agent,
                        target_agent_uuid=available_agents[target_agent],
                        current_agent_id=current_agent_id,
                    )
                    return target_agent
                else:
                    logger.warning(
                        "Invalid target agent in structured routing",
                        routing_response=agent_response,
                        target_agent=target_agent,
                        available_agents=list(available_agents.keys()),
                    )
                break

    logger.warning(
        "No valid routing signal detected - ignoring",
        routing_response=agent_response,
        available_agents=list(available_agents.keys()),
        current_agent_id=current_agent_id,
    )

    return None
