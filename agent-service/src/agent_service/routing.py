"""Agent routing detection and validation logic for Agent Service."""

import os
from typing import Optional

import structlog
from shared_models import AgentMapping

logger = structlog.get_logger()


async def detect_and_validate_agent_routing(
    content: str,
    current_agent_id: str,
    available_agents: AgentMapping,
) -> Optional[str]:
    """Detect routing signals in agent responses.

    Supports two routing signals (matching session-manager approach):
    1. task_complete_return_to_router - routes back to routing agent (from any agent)
    2. Direct agent name - routes to specific agent (from routing agent)
    """

    agent_response = content.strip()

    # Check for task completion signal first (from any agent)
    # Look for signal as exact match or at the end of the response
    signal = agent_response.lower()
    if signal == "task_complete_return_to_router" or signal.endswith(
        "task_complete_return_to_router"
    ):
        logger.info(
            "Task completion signal detected - routing back to router",
            current_agent_id=current_agent_id,
            response=agent_response,
        )
        # Use the default agent ID from environment (same as agent service)
        default_agent = os.getenv("DEFAULT_AGENT_ID", "routing-agent")
        return default_agent

    # Extract routing signal, handling both single responses and multi-line responses
    # This matches the session-manager logic exactly

    # If response contains multiple lines, look for agent names in the response
    if "\n" in signal:
        lines = signal.split("\n")
        # Look for lines that match agent names
        for line in lines:
            line = line.strip()
            if line in [name.lower() for name in available_agents.get_all_names()]:
                signal = line
                break
        else:
            # If no agent name found in lines, use first line (fallback)
            signal = lines[0].strip()

    # If no agent found yet, check if any agent name appears at the end of the response
    agent_names_lower = [name.lower() for name in available_agents.get_all_names()]
    if signal not in agent_names_lower:
        for agent_name in available_agents.get_all_names():
            if signal.endswith(agent_name.lower()):
                signal = agent_name.lower()
                break

    # Check for direct agent name routing (case-insensitive)
    # Look for agent name as exact match
    for agent_name in available_agents.get_all_names():
        if signal == agent_name.lower():
            # Get current agent name to check if we're already on this agent
            current_agent_name = (
                available_agents.get_name(current_agent_id)
                if current_agent_id
                else None
            )

            # Don't route to the same agent we're already on
            if current_agent_name and agent_name.lower() == current_agent_name.lower():
                logger.debug(
                    "Ignoring routing to same agent",
                    routing_response=agent_response,
                    target_agent=agent_name,
                    current_agent_id=current_agent_id,
                    current_agent_name=current_agent_name,
                )
                continue

            # Don't route to routing agent from routing agent
            if (
                agent_name.lower()
                == os.getenv("DEFAULT_AGENT_ID", "routing-agent").lower()
            ):
                logger.debug(
                    "Ignoring routing to routing agent from routing agent",
                    routing_response=agent_response,
                    target_agent=agent_name,
                    current_agent_id=current_agent_id,
                )
                continue

            target_uuid = available_agents.get_uuid(agent_name)
            logger.info(
                "Direct agent routing detected",
                routing_response=agent_response,
                target_agent_name=agent_name,
                target_agent_uuid=target_uuid,
                current_agent_id=current_agent_id,
                current_agent_name=current_agent_name,
            )
            return agent_name

    logger.debug(
        "No valid routing signal detected - ignoring",
        routing_response=agent_response,
        available_agents=available_agents.get_all_names(),
        current_agent_id=current_agent_id,
    )

    return None
