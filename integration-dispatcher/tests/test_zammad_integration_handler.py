"""Tests for Zammad REST delivery handler."""

import os
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integration_dispatcher.integrations.zammad import ZammadIntegrationHandler
from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig


@pytest.fixture
def handler() -> ZammadIntegrationHandler:
    return ZammadIntegrationHandler()


@pytest.fixture
def mock_config() -> UserIntegrationConfig:
    # Handler only needs a config object for the signature; deliver() does not read fields.
    return cast(UserIntegrationConfig, MagicMock())


@pytest.mark.asyncio
async def test_skips_when_not_ticket_thread_binding(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="s1",
        user_id="user@test.com-81",
        content="Hello",
        integration_context={"delivery_binding": "STANDARD"},
    )
    result = await handler.deliver(req, mock_config, {"subject": "", "body": "Hello"})
    assert result.success is True
    assert result.metadata.get("delivery_method") == "zammad_skip_non_ticket"


@pytest.mark.asyncio
async def test_posts_ticket_article_minimal_payload(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="user@test.com-81",
        content="Visible reply",
        agent_id="ticket-laptop-refresh",
        integration_context={"delivery_binding": "TICKET_THREAD", "ticket_id": 81},
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 999}
    mock_resp.raise_for_status = MagicMock()

    ticket_resp = MagicMock()
    ticket_resp.status_code = 200
    ticket_resp.raise_for_status = MagicMock()
    ticket_resp.json.return_value = {"id": 81, "owner_id": 1, "owner": None}

    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=ticket_resp)
    mock_http.post = AsyncMock(return_value=mock_resp)

    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "http://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "secret-token",
        },
        clear=False,
    ):
        with patch(
            "integration_dispatcher.integrations.zammad.get_zammad_rest_service_client",
            new_callable=AsyncMock,
        ) as mock_get_client:
            mock_get_client.return_value = mock_http

            result = await handler.deliver(
                req, mock_config, {"subject": "", "body": "Visible reply"}
            )

    assert result.success is True
    assert result.status == DeliveryStatus.DELIVERED
    assert result.metadata.get("zammad_article_id") == 999
    assert result.metadata.get("responding_agent_id") == "ticket-laptop-refresh"
    assert "origin_by_id" not in result.metadata
    mock_http.get.assert_awaited_once()
    assert mock_http.get.await_args[0][0] == "/tickets/81"
    mock_http.post.assert_awaited_once()
    call_kw = mock_http.post.await_args
    assert call_kw[0][0] == "/ticket_articles"
    payload = call_kw[1]["json"]
    assert payload == {
        "ticket_id": 81,
        "body": "Visible reply",
        "type": "note",
        "internal": False,
        "sender": "Agent",
    }
    headers = call_kw[1]["headers"]
    assert "From" not in headers


@pytest.mark.asyncio
async def test_fails_without_credentials(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="u1",
        content="Hi",
        integration_context={"delivery_binding": "TICKET_THREAD", "ticket_id": 5},
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZAMMAD_")}
    with patch.dict(os.environ, env, clear=True):
        result = await handler.deliver(req, mock_config, {"body": "Hi"})
    assert result.success is False


@pytest.mark.asyncio
async def test_posts_on_behalf_of_owner_email_from_integration_context(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="user@test.com-81",
        content="Visible reply",
        agent_id="ticket-laptop-refresh",
        integration_context={
            "delivery_binding": "TICKET_THREAD",
            "ticket_id": 81,
            "owner_email": "specialist@example.com",
        },
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 1001}
    mock_resp.raise_for_status = MagicMock()

    mock_http = MagicMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    mock_http.get = AsyncMock()

    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "http://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "secret-token",
        },
        clear=False,
    ):
        with patch(
            "integration_dispatcher.integrations.zammad.get_zammad_rest_service_client",
            new_callable=AsyncMock,
        ) as mock_get_client:
            mock_get_client.return_value = mock_http
            result = await handler.deliver(req, mock_config, {"body": "Visible reply"})

    assert result.success is True
    assert result.metadata.get("on_behalf_of") == "specialist@example.com"
    mock_http.get.assert_not_awaited()
    headers = mock_http.post.await_args[1]["headers"]
    assert headers["From"] == "specialist@example.com"


@pytest.mark.asyncio
async def test_posts_on_behalf_of_owner_resolved_from_owner_id(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="user@test.com-81",
        content="Visible reply",
        agent_id="ticket-laptop-refresh",
        integration_context={
            "delivery_binding": "TICKET_THREAD",
            "ticket_id": 81,
            "owner_id": 23,
        },
    )

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post_resp.json.return_value = {"id": 1002}
    mock_post_resp.raise_for_status = MagicMock()

    user_resp = MagicMock()
    user_resp.status_code = 200
    user_resp.raise_for_status = MagicMock()
    user_resp.json.return_value = {
        "id": 23,
        "email": "assigned.specialist@example.com",
    }

    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=user_resp)
    mock_http.post = AsyncMock(return_value=mock_post_resp)

    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "http://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "secret-token",
        },
        clear=False,
    ):
        with patch(
            "integration_dispatcher.integrations.zammad.get_zammad_rest_service_client",
            new_callable=AsyncMock,
        ) as mock_get_client:
            mock_get_client.return_value = mock_http
            result = await handler.deliver(req, mock_config, {"body": "Visible reply"})

    assert result.success is True
    assert result.metadata.get("on_behalf_of") == "assigned.specialist@example.com"
    mock_http.get.assert_awaited_once()
    get_path = mock_http.get.await_args[0][0]
    assert get_path == "/users/23"
    headers = mock_http.post.await_args[1]["headers"]
    assert headers["From"] == "assigned.specialist@example.com"


@pytest.mark.asyncio
async def test_snapshot_owner_email_wins_over_live_ticket_owner(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    """Intake assignee in integration_context is used even if ticket was reassigned in Zammad."""
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="user@test.com-81",
        content="Visible reply",
        agent_id="ticket-laptop-refresh",
        integration_context={
            "delivery_binding": "TICKET_THREAD",
            "ticket_id": 81,
            "owner_email": "original@example.com",
        },
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 2001}
    mock_resp.raise_for_status = MagicMock()

    mock_http = MagicMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    mock_http.get = AsyncMock()

    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "http://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "secret-token",
        },
        clear=False,
    ):
        with patch(
            "integration_dispatcher.integrations.zammad.get_zammad_rest_service_client",
            new_callable=AsyncMock,
        ) as mock_get_client:
            mock_get_client.return_value = mock_http
            result = await handler.deliver(req, mock_config, {"body": "Visible reply"})

    assert result.success is True
    assert result.metadata.get("on_behalf_of") == "original@example.com"
    mock_http.get.assert_not_awaited()
    assert mock_http.post.await_args[1]["headers"]["From"] == "original@example.com"


@pytest.mark.asyncio
async def test_retries_without_on_behalf_when_forbidden(
    handler: ZammadIntegrationHandler,
    mock_config: UserIntegrationConfig,
) -> None:
    req = DeliveryRequest(
        request_id="r1",
        session_id="zammad-81",
        user_id="user@test.com-81",
        content="Visible reply",
        agent_id="ticket-laptop-refresh",
        integration_context={
            "delivery_binding": "TICKET_THREAD",
            "ticket_id": 81,
            "owner_email": "specialist@example.com",
        },
    )

    forbidden_resp = MagicMock()
    forbidden_resp.status_code = 403
    forbidden_resp.raise_for_status = MagicMock()

    ok_resp = MagicMock()
    ok_resp.status_code = 201
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {"id": 1003}

    mock_http = MagicMock()
    mock_http.get = AsyncMock()
    mock_http.post = AsyncMock(side_effect=[forbidden_resp, ok_resp])

    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "http://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "secret-token",
        },
        clear=False,
    ):
        with patch(
            "integration_dispatcher.integrations.zammad.get_zammad_rest_service_client",
            new_callable=AsyncMock,
        ) as mock_get_client:
            mock_get_client.return_value = mock_http
            result = await handler.deliver(req, mock_config, {"body": "Visible reply"})

    assert result.success is True
    assert result.metadata.get("on_behalf_of") is None
    assert mock_http.post.await_count == 2
    mock_http.get.assert_not_awaited()
    first_headers = mock_http.post.await_args_list[0].kwargs["headers"]
    second_headers = mock_http.post.await_args_list[1].kwargs["headers"]
    assert first_headers["From"] == "specialist@example.com"
    assert "From" not in second_headers
