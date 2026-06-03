"""HTTP and CloudEvent session paths both use resolve_ticket_scoped_session for PER_TICKET."""

from unittest.mock import AsyncMock, patch

import pytest
from request_manager.communication_strategy import create_or_get_session_shared
from request_manager.schemas import WebRequest
from shared_models.channel_behavior import SessionScope
from shared_models.models import IntegrationType


@pytest.mark.asyncio
async def test_http_per_ticket_calls_resolve_ticket_scoped_session() -> None:
    request = WebRequest(
        user_id="user@test.com",
        content="hi",
        session_token=None,
        client_ip=None,
        user_agent=None,
    )
    request.metadata = {"ticket_id": 7}
    db = AsyncMock()

    policy = AsyncMock()
    policy.session_scope = SessionScope.PER_TICKET

    with (
        patch(
            "shared_models.resolve_canonical_user_id",
            new_callable=AsyncMock,
            return_value="canonical-1",
        ),
        patch(
            "request_manager.communication_strategy.resolve_channel_behavior",
            new_callable=AsyncMock,
            return_value=policy,
        ),
        patch(
            "request_manager.communication_strategy.parse_ticket_id",
            return_value=7,
        ),
        patch(
            "request_manager.communication_strategy.resolve_ticket_scoped_session",
            new_callable=AsyncMock,
        ) as mock_ticket,
    ):
        mock_ticket.return_value = AsyncMock(session_id="zammad-7")
        await create_or_get_session_shared(request, db)

    mock_ticket.assert_awaited_once()
    call = mock_ticket.await_args
    assert call is not None
    assert call.kwargs["integration_type"] == IntegrationType.WEB


@pytest.mark.asyncio
async def test_cloudevent_per_ticket_calls_resolve_ticket_scoped_session() -> None:
    from request_manager.session_events import _handle_session_create_or_get_event

    db = AsyncMock()
    event = {
        "id": "evt-1",
        "correlationid": "corr-1",
        "data": {
            "user_id": "user@test.com",
            "integration_type": "ZAMMAD",
            "integration_metadata": {"ticket_id": 12},
        },
    }

    policy = AsyncMock()
    policy.session_scope = SessionScope.PER_TICKET

    with (
        patch(
            "request_manager.session_events.resolve_canonical_user_id",
            new_callable=AsyncMock,
            return_value="canonical-1",
        ),
        patch(
            "request_manager.session_events.resolve_channel_behavior",
            new_callable=AsyncMock,
            return_value=policy,
        ),
        patch(
            "request_manager.session_events.parse_ticket_id_from_metadata",
            return_value=12,
        ),
        patch(
            "request_manager.session_events.resolve_ticket_scoped_session",
            new_callable=AsyncMock,
        ) as mock_ticket,
        patch(
            "request_manager.session_events._publish_session_ready_event",
            new_callable=AsyncMock,
        ),
        patch(
            "request_manager.session_events.create_cloudevent_response",
            new_callable=AsyncMock,
            return_value={"status": "success"},
        ),
    ):
        mock_ticket.return_value = AsyncMock(session_id="zammad-12")
        await _handle_session_create_or_get_event(event, db)

    mock_ticket.assert_awaited_once()
    call = mock_ticket.await_args
    assert call is not None
    assert call.kwargs["integration_type"] == IntegrationType.ZAMMAD
