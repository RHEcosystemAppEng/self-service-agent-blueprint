"""Request Manager session paths driven by channel behavior policy."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from request_manager.communication_strategy import create_or_get_session_shared
from request_manager.schemas import WebRequest
from shared_models.channel_behavior import SessionScope


@pytest.mark.asyncio
async def test_per_ticket_without_ticket_id_returns_400() -> None:
    request = WebRequest(
        user_id="user@test.com",
        content="hi",
        session_token=None,
        client_ip=None,
        user_agent=None,
    )
    request.metadata = {}

    db = AsyncMock()

    with (
        patch(
            "shared_models.resolve_canonical_user_id",
            new=AsyncMock(return_value="user@test.com"),
        ),
        patch(
            "request_manager.communication_strategy.resolve_channel_behavior",
            new=AsyncMock(
                return_value=MagicMock(session_scope=SessionScope.PER_TICKET)
            ),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_or_get_session_shared(request, db)

    assert exc_info.value.status_code == 400
    assert "ticket_id" in str(exc_info.value.detail).lower()
