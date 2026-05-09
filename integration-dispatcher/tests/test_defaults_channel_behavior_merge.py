"""Integration defaults upsert must not store channel_behavior (registry owns policy)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integration_dispatcher.integrations.defaults import IntegrationDefaultsService
from shared_models.models import IntegrationType


@pytest.mark.asyncio
async def test_refresh_preserves_existing_channel_behavior() -> None:
    service = IntegrationDefaultsService()
    service.default_integrations = {
        "SLACK": {
            "priority": 1,
            "retry_count": 3,
            "retry_delay_seconds": 60,
            "config": {"slack_delivery": True},
        },
    }

    existing_row = MagicMock()
    existing_row.integration_type = IntegrationType.SLACK
    existing_row.config = {
        "slack_delivery": False,
        "channel_behavior": {
            "schema_version": 1,
            "session_scope": "PER_USER",
            "delivery_binding": "STANDARD",
        },
    }

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [existing_row]
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()

    captured_values: list[dict[str, Any]] = []

    def capture_values(upsert_values: list[dict[str, Any]]) -> MagicMock:
        captured_values.extend(upsert_values)
        stmt = MagicMock()
        stmt.on_conflict_do_update.return_value = stmt
        return stmt

    with (
        patch.object(
            service,
            "_check_integration_health",
            new=AsyncMock(return_value={"SLACK": True}),
        ),
        patch(
            "integration_dispatcher.integrations.defaults.insert",
        ) as mock_insert,
    ):
        mock_insert.return_value.values.side_effect = capture_values
        await service._refresh_default_configs(db)

    assert len(captured_values) == 1
    cfg = captured_values[0]["config"]
    assert cfg["channel_behavior"] == existing_row.config["channel_behavior"]
    assert cfg["slack_delivery"] is True


@pytest.mark.asyncio
async def test_refresh_strips_channel_behavior_from_defaults_payload() -> None:
    service = IntegrationDefaultsService()
    service.default_integrations = {
        "ZAMMAD": {
            "priority": 1,
            "retry_count": 3,
            "retry_delay_seconds": 60,
            "config": {
                "zammad_delivery": True,
                "channel_behavior": {"session_scope": "PER_TICKET"},
            },
        },
    }

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()

    captured_values: list[dict[str, Any]] = []

    def capture_values(upsert_values: list[dict[str, Any]]) -> MagicMock:
        captured_values.extend(upsert_values)
        stmt = MagicMock()
        stmt.on_conflict_do_update.return_value = stmt
        return stmt

    with (
        patch.object(
            service,
            "_check_integration_health",
            new=AsyncMock(return_value={"ZAMMAD": True}),
        ),
        patch(
            "integration_dispatcher.integrations.defaults.insert",
        ) as mock_insert,
    ):
        mock_insert.return_value.values.side_effect = capture_values
        await service._refresh_default_configs(db)

    assert len(captured_values) == 1
    assert "channel_behavior" not in captured_values[0]["config"]
