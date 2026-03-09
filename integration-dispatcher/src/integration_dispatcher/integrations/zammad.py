"""Zammad integration handler - no-op.

Zammad responses are delivered via MCP (zammad_add_article) by the agent.
This handler exists to satisfy the dispatcher's handler lookup; it returns
success immediately without delivering.
"""

from typing import Any, Dict

from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig

from .base import BaseIntegrationHandler, IntegrationResult


class ZammadIntegrationHandler(BaseIntegrationHandler):
    """No-op handler for Zammad. Agent delivers via MCP directly."""

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """No-op: agent already delivered via zammad_add_article."""
        return IntegrationResult(
            success=True,
            status=DeliveryStatus.DELIVERED,
            message="Zammad delivery via MCP (no-op)",
            metadata={"delivery_method": "zammad_mcp"},
        )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Zammad requires no config for delivery (MCP handles it)."""
        return True
