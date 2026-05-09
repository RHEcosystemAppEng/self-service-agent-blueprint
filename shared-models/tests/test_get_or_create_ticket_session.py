"""Tests for per-ticket session helper."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shared_models.models import IntegrationType, SessionStatus
from shared_models.session_manager import (
    get_or_create_ticket_session,
    ticket_session_id,
)


def test_ticket_session_id_format() -> None:
    assert ticket_session_id(IntegrationType.ZAMMAD, 42) == "zammad-42"


@pytest.mark.asyncio
async def test_get_or_create_ticket_session_returns_existing() -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    existing = MagicMock()
    existing.session_id = "zammad-99"
    existing.user_id = "user-1"
    existing.status = SessionStatus.ACTIVE.value

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = existing
    touch_result = MagicMock()
    touched = MagicMock()
    touched.session_id = "zammad-99"
    touch_result.scalar_one_or_none.return_value = touched
    db.execute = AsyncMock(side_effect=[select_result, touch_result])

    expected = MagicMock(session_id="zammad-99")
    with patch(
        "shared_models.session_manager.SessionResponse.model_validate",
        return_value=expected,
    ):
        result = await get_or_create_ticket_session(
            db,
            integration_type=IntegrationType.ZAMMAD,
            canonical_user_id="user-1",
            ticket_id=99,
            channel_id=None,
            thread_id=None,
            integration_metadata={},
            user_context={},
            expires_at=expires_at,
        )

    assert result.session_id == "zammad-99"
    assert db.commit.await_count == 1
