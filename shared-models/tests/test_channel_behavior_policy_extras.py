"""session_isolated_by_integration_type, DB override, solo-pool helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from shared_models.channel_behavior import (
    ChannelBehaviorPolicy,
    SessionScope,
    channel_behavior_allow_db_override,
    resolve_channel_behavior,
    should_filter_sessions_by_integration_type,
)
from shared_models.channel_behavior_session import (
    should_filter_lookup_by_integration_type,
)
from shared_models.models import IntegrationDefaultConfig, IntegrationType


def test_session_isolated_flag_enables_solo_pool_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SESSION_PER_INTEGRATION_TYPE", raising=False)
    policy = ChannelBehaviorPolicy(session_isolated_by_integration_type=True)
    assert should_filter_sessions_by_integration_type(policy) is True
    assert should_filter_lookup_by_integration_type(policy) is True


def test_session_isolated_false_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_PER_INTEGRATION_TYPE", "true")
    policy = ChannelBehaviorPolicy(session_isolated_by_integration_type=False)
    assert should_filter_sessions_by_integration_type(policy) is True


@pytest.mark.asyncio
async def test_db_override_merges_channel_behavior_from_defaults_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE", "true")
    assert channel_behavior_allow_db_override() is True

    row = MagicMock(spec=IntegrationDefaultConfig)
    row.config = {
        "channel_behavior": {
            "schema_version": 1,
            "session_scope": "PER_USER",
            "session_isolated_by_integration_type": True,
        }
    }
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row))
    )

    policy = await resolve_channel_behavior(IntegrationType.WEB, db)
    assert policy.session_isolated_by_integration_type is True
    assert policy.session_scope == SessionScope.PER_USER
