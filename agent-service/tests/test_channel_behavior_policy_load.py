"""Agent-service loads channel behavior from session snapshot only."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_service.session_manager import ResponsesSessionManager
from shared_models.channel_behavior import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    SessionScope,
    build_integration_metadata_with_policy,
)


@pytest.mark.asyncio
async def test_load_policy_raises_when_snapshot_missing() -> None:
    db = AsyncMock()
    manager = ResponsesSessionManager(db, user_id="user@test.com")
    row = MagicMock()
    row.integration_type = "WEB"
    row.integration_metadata = {}

    with patch.object(manager, "get_session", new=AsyncMock(return_value=row)):
        with pytest.raises(ChannelBehaviorValidationError, match="missing"):
            await manager._load_policy_from_request_session("sess-1")


@pytest.mark.asyncio
async def test_load_policy_from_snapshot() -> None:
    db = AsyncMock()
    manager = ResponsesSessionManager(db, user_id="user@test.com")
    pol = ChannelBehaviorPolicy(
        session_scope=SessionScope.PER_TICKET,
        allow_return_to_router=False,
    )
    meta = build_integration_metadata_with_policy({}, pol)
    row = MagicMock()
    row.integration_type = "ZAMMAD"
    row.integration_metadata = meta

    with patch.object(manager, "get_session", new=AsyncMock(return_value=row)):
        await manager._load_policy_from_request_session("zammad-1")

    assert manager._channel_policy is not None
    assert manager._channel_policy.session_scope == SessionScope.PER_TICKET
    assert CHANNEL_BEHAVIOR_SNAPSHOT_KEY in meta
