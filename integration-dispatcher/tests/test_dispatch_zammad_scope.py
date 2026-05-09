"""Dispatch scoping: Zammad ticket replies must not fan out to other channels."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integration_dispatcher.main import IntegrationDispatcher
from shared_models.models import DeliveryRequest, IntegrationType


@pytest.mark.asyncio
async def test_zammad_ticket_dispatches_zammad_only() -> None:
    dispatcher = IntegrationDispatcher()

    slack_cfg = MagicMock()
    slack_cfg.integration_type = IntegrationType.SLACK
    zammad_cfg = MagicMock()
    zammad_cfg.integration_type = IntegrationType.ZAMMAD

    get_cfgs = AsyncMock(return_value=[slack_cfg, zammad_cfg])
    dispatch_single = AsyncMock(return_value={"success": True})

    req = DeliveryRequest(
        request_id="req-1",
        session_id="zammad-42",
        user_id="alice@example.com-42",
        content="Hello from the agent",
        integration_context={"delivery_binding": "TICKET_THREAD", "ticket_id": 42},
    )
    with (
        patch.object(dispatcher, "_get_user_integration_configs", new=get_cfgs),
        patch.object(dispatcher, "_dispatch_single", new=dispatch_single),
    ):
        await dispatcher.dispatch(req, AsyncMock())

    dispatch_single.assert_awaited_once()
    aa = dispatch_single.await_args
    assert aa is not None
    called_cfg = aa.args[1]
    assert called_cfg.integration_type == IntegrationType.ZAMMAD


@pytest.mark.asyncio
async def test_slack_session_excludes_zammad_even_if_configured() -> None:
    dispatcher = IntegrationDispatcher()

    slack_cfg = MagicMock()
    slack_cfg.integration_type = IntegrationType.SLACK
    zammad_cfg = MagicMock()
    zammad_cfg.integration_type = IntegrationType.ZAMMAD

    get_cfgs = AsyncMock(return_value=[slack_cfg, zammad_cfg])
    dispatch_single = AsyncMock(return_value={"success": True})

    req = DeliveryRequest(
        request_id="req-2",
        session_id="sess-1",
        user_id="user-1",
        content="Hi",
        integration_context={"delivery_binding": "STANDARD", "channel_id": "C1"},
    )
    with (
        patch.object(dispatcher, "_get_user_integration_configs", new=get_cfgs),
        patch.object(dispatcher, "_dispatch_single", new=dispatch_single),
    ):
        await dispatcher.dispatch(req, AsyncMock())

    dispatch_single.assert_awaited_once()
    aa = dispatch_single.await_args
    assert aa is not None
    assert aa.args[1].integration_type == IntegrationType.SLACK


@pytest.mark.asyncio
async def test_empty_integration_context_excludes_zammad() -> None:
    dispatcher = IntegrationDispatcher()

    zammad_cfg = MagicMock()
    zammad_cfg.integration_type = IntegrationType.ZAMMAD

    get_cfgs = AsyncMock(return_value=[zammad_cfg])
    dispatch_single = AsyncMock(return_value={"success": True})

    req = DeliveryRequest(
        request_id="req-3",
        session_id="sess-2",
        user_id="user-2",
        content="Hi",
        integration_context={},
    )
    with (
        patch.object(dispatcher, "_get_user_integration_configs", new=get_cfgs),
        patch.object(dispatcher, "_dispatch_single", new=dispatch_single),
    ):
        await dispatcher.dispatch(req, AsyncMock())

    dispatch_single.assert_not_awaited()
