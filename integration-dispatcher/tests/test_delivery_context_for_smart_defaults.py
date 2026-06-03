"""Delivery path must pass delivery_binding into smart-defaults context."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integration_dispatcher.main import IntegrationDispatcher
from shared_models.models import DeliveryRequest, IntegrationType


@pytest.mark.asyncio
async def test_get_user_integration_configs_passes_delivery_binding() -> None:
    dispatcher = IntegrationDispatcher()
    captured_context: dict[str, Any] = {}

    async def capture_smart_defaults(
        user_id: str,
        db: object = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured_context.update(context or {})
        zammad_cfg = MagicMock()
        zammad_cfg.integration_type = IntegrationType.ZAMMAD
        zammad_cfg.enabled = True
        zammad_cfg.priority = 1
        zammad_cfg.retry_count = 3
        zammad_cfg.retry_delay_seconds = 60
        zammad_cfg.config = {}
        return {
            "ZAMMAD": {
                "integration_type": IntegrationType.ZAMMAD,
                "enabled": True,
                "priority": 1,
                "retry_count": 3,
                "retry_delay_seconds": 60,
                "config": {},
            }
        }

    req = DeliveryRequest(
        request_id="req-1",
        session_id="zammad-2",
        user_id="canonical-user",
        content="reply",
        integration_context={
            "ticket_id": 2,
            "delivery_binding": "TICKET_THREAD",
        },
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    with patch(
        "integration_dispatcher.main.integration_defaults_service.get_smart_defaults",
        new=capture_smart_defaults,
    ):
        configs = await dispatcher._get_user_integration_configs(
            "canonical-user", db, req
        )

    assert captured_context["ticket_id"] == 2
    assert captured_context["delivery_binding"] == "TICKET_THREAD"
    assert len(configs) == 1
    assert configs[0].integration_type == IntegrationType.ZAMMAD
