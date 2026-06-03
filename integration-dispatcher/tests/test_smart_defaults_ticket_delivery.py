"""Smart defaults enable ticket backends only for TICKET_THREAD delivery context."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integration_dispatcher.integrations.defaults import IntegrationDefaultsService
from shared_models.models import IntegrationDefaultConfig, IntegrationType


@pytest.mark.asyncio
async def test_smart_defaults_disables_zammad_without_ticket_context() -> None:
    service = IntegrationDefaultsService()
    zammad_row = MagicMock(spec=IntegrationDefaultConfig)
    zammad_row.integration_type = IntegrationType.ZAMMAD
    zammad_row.enabled = True
    zammad_row.priority = 1
    zammad_row.retry_count = 3
    zammad_row.retry_delay_seconds = 60
    zammad_row.config = {}

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [zammad_row]
    db.execute = AsyncMock(return_value=result)

    with patch.object(
        service,
        "_check_integration_health",
        new=AsyncMock(return_value={"ZAMMAD": True}),
    ):
        out = await service.get_smart_defaults(
            "user-1",
            db=db,
            context={"delivery_binding": "STANDARD"},
        )

    assert "ZAMMAD" not in out


@pytest.mark.asyncio
async def test_smart_defaults_enables_zammad_for_ticket_thread() -> None:
    service = IntegrationDefaultsService()
    zammad_row = MagicMock(spec=IntegrationDefaultConfig)
    zammad_row.integration_type = IntegrationType.ZAMMAD
    zammad_row.enabled = True
    zammad_row.priority = 1
    zammad_row.retry_count = 3
    zammad_row.retry_delay_seconds = 60
    zammad_row.config = {}

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [zammad_row]
    db.execute = AsyncMock(return_value=result)

    with patch.object(
        service,
        "_check_integration_health",
        new=AsyncMock(return_value={"ZAMMAD": True}),
    ):
        out = await service.get_smart_defaults(
            "user-1",
            db=db,
            context={
                "delivery_binding": "TICKET_THREAD",
                "ticket_id": 42,
            },
        )

    assert "ZAMMAD" in out
    assert out["ZAMMAD"]["enabled"] is True
