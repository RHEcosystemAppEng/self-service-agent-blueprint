"""Unified PER_USER session lookup (shared HTTP + CloudEvent path)."""

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
from shared_models.channel_behavior_session import find_active_per_user_sessions
from shared_models.models import IntegrationType, SessionStatus


def _row(
    session_id: str,
    integration_type: IntegrationType,
    metadata: dict[str, Any] | None = None,
) -> MagicMock:
    r = MagicMock()
    r.session_id = session_id
    r.integration_type = integration_type
    r.integration_metadata = metadata or {}
    r.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    r.status = SessionStatus.ACTIVE.value
    return r


@pytest.mark.asyncio
async def test_unified_pool_excludes_ticket_scoped_rows() -> None:
    web_meta = build_integration_metadata_with_policy(
        {},
        ChannelBehaviorPolicy(session_scope=SessionScope.PER_USER),
    )
    web = _row("web-1", IntegrationType.WEB, web_meta)
    ticket_meta = build_integration_metadata_with_policy(
        {},
        ChannelBehaviorPolicy(
            session_scope=SessionScope.PER_TICKET,
            delivery_binding=DeliveryBinding.TICKET_THREAD,
            exclude_from_unified_session_pool=True,
        ),
    )
    ticket = _row("zammad-9", IntegrationType.ZAMMAD, ticket_meta)

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [ticket, web]
    db.execute = AsyncMock(return_value=result)

    found = await find_active_per_user_sessions(
        db,
        canonical_user_id="user-1",
        integration_type=IntegrationType.SLACK,
        filter_by_integration_type=False,
    )
    assert len(found) == 1
    assert found[0].session_id == "web-1"
