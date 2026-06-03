"""Tests for channel behavior session helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from shared_models.channel_behavior import (
    ChannelBehaviorPolicy,
    DeliveryBinding,
    SessionScope,
    build_integration_metadata_with_policy,
)
from shared_models.channel_behavior_session import (
    SessionPinScopeMismatchError,
    row_excluded_from_unified_pool,
    validate_explicit_session_pin,
)
from shared_models.models import IntegrationType


def _mock_session(
    *,
    session_id: str = "sess-web",
    integration_type: IntegrationType = IntegrationType.WEB,
    metadata: dict[str, Any] | None = None,
) -> MagicMock:
    s = MagicMock()
    s.session_id = session_id
    s.integration_type = integration_type
    s.integration_metadata = metadata or {}
    s.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    s.status = "ACTIVE"
    s.user_id = "user-1"
    return s


@pytest.mark.asyncio
async def test_reject_pin_to_session_without_snapshot() -> None:
    row = _mock_session(session_id="sess-1", metadata={})
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(SessionPinScopeMismatchError, match="missing _channel_behavior"):
        await validate_explicit_session_pin(
            db,
            canonical_user_id="user-1",
            provided_session_id="sess-1",
            inbound_integration_type=IntegrationType.WEB,
            inbound_policy=ChannelBehaviorPolicy(),
        )


@pytest.mark.asyncio
async def test_reject_pin_web_to_ticket_scoped_session() -> None:
    ticket_policy = ChannelBehaviorPolicy(
        entry_agent_id="ticket-review-agent",
        session_scope=SessionScope.PER_TICKET,
        exclude_from_unified_session_pool=True,
        delivery_binding=DeliveryBinding.TICKET_THREAD,
        allow_return_to_router=False,
    )
    meta = build_integration_metadata_with_policy({}, ticket_policy)
    row = _mock_session(
        session_id="zammad-42",
        integration_type=IntegrationType.ZAMMAD,
        metadata=meta,
    )

    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)

    web_policy = ChannelBehaviorPolicy(session_scope=SessionScope.PER_USER)
    with pytest.raises(SessionPinScopeMismatchError, match="integration_type mismatch"):
        await validate_explicit_session_pin(
            db,
            canonical_user_id="user-1",
            provided_session_id="zammad-42",
            inbound_integration_type=IntegrationType.WEB,
            inbound_policy=web_policy,
        )


def test_row_excluded_without_snapshot_fail_closed() -> None:
    """Rows without snapshot are excluded from unified pool (fail closed)."""
    row = _mock_session(
        session_id="zammad-42",
        integration_type=IntegrationType.WEB,
        metadata={},
    )
    assert row_excluded_from_unified_pool(row) is True


def test_row_excluded_from_snapshot_flag() -> None:
    pol = ChannelBehaviorPolicy(exclude_from_unified_session_pool=True)
    meta = build_integration_metadata_with_policy({}, pol)
    row = _mock_session(integration_type=IntegrationType.SLACK, metadata=meta)
    assert row_excluded_from_unified_pool(row) is True
