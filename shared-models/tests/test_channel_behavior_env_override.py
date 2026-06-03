"""CHANNEL_BEHAVIOR_OVERRIDES env merged at resolve time."""

import pytest
from shared_models.channel_behavior import (
    _channel_behavior_overrides_from_env,
    resolve_channel_behavior,
)
from shared_models.models import IntegrationType


@pytest.mark.asyncio
async def test_env_override_merges_over_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _channel_behavior_overrides_from_env.cache_clear()
    monkeypatch.setenv(
        "CHANNEL_BEHAVIOR_OVERRIDES",
        '{"SLACK": {"session_isolated_by_integration_type": true}}',
    )
    _channel_behavior_overrides_from_env.cache_clear()

    policy = await resolve_channel_behavior(IntegrationType.SLACK, db=None)
    assert policy.session_isolated_by_integration_type is True

    _channel_behavior_overrides_from_env.cache_clear()
    monkeypatch.delenv("CHANNEL_BEHAVIOR_OVERRIDES", raising=False)


@pytest.mark.asyncio
async def test_db_override_wins_over_env_when_both_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from shared_models.models import IntegrationDefaultConfig

    _channel_behavior_overrides_from_env.cache_clear()
    monkeypatch.setenv(
        "CHANNEL_BEHAVIOR_OVERRIDES",
        '{"WEB": {"session_isolated_by_integration_type": false}}',
    )
    monkeypatch.setenv("CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE", "true")
    _channel_behavior_overrides_from_env.cache_clear()

    row = MagicMock(spec=IntegrationDefaultConfig)
    row.config = {"channel_behavior": {"session_isolated_by_integration_type": True}}
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row))
    )

    policy = await resolve_channel_behavior(IntegrationType.WEB, db)
    assert policy.session_isolated_by_integration_type is True

    _channel_behavior_overrides_from_env.cache_clear()
    monkeypatch.delenv("CHANNEL_BEHAVIOR_OVERRIDES", raising=False)
    monkeypatch.delenv("CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE", raising=False)
