"""Tests for Zammad MCP wrapper tools (mocked Basher MCP + REST auth)."""

import json
import os
from dataclasses import replace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from zammad_mcp.server import (
    close,
    escalate_for_human_review,
    get_employee_laptop_info,
    mark_as_agent_managed_laptop_refresh,
    mark_as_general_agent_managed,
    route_to_human_managed_queue,
    send_to_manager_review,
)
from zammad_mcp.settings import load_zammad_mcp_settings


class MockRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class MockRequestContext:
    def __init__(self, headers: dict[str, str]):
        self.request = MockRequest(headers)


class MockContext:
    def __init__(self, headers: dict[str, str]):
        self.request_context = MockRequestContext(headers)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"AUTHORITATIVE_USER_ID": "alice@company.com-100"}


@pytest.fixture(autouse=True)
def zammad_url() -> Any:
    with patch.dict(
        os.environ,
        {
            "ZAMMAD_URL": "https://zammad.example.com",
            "ZAMMAD_HTTP_TOKEN": "test-token",
        },
        clear=False,
    ):
        yield


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_mark_as_agent_managed(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)

    result = mark_as_agent_managed_laptop_refresh(ctx)

    mock_assert.assert_called_once()
    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == [
        "zammad_add_ticket_tag",
        "zammad_update_ticket",
        "zammad_update_ticket",
    ]
    assert mock_basher.call_args_list[0][0][1] == {
        "ticket_id": 100,
        "tag": "agent-managed-laptop-refresh",
    }
    assert mock_basher.call_args_list[1][0][1] == {
        "ticket_id": 100,
        "state": "open",
    }
    assert mock_basher.call_args_list[2][0][1] == {
        "ticket_id": 100,
        "owner": "agent.laptop-specialist@example.com",
    }
    assert "tagged" in result.lower() or "Ticket 100" in result


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_mark_as_agent_managed_state_only_when_owner_empty(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    """When laptop specialist owner is empty, update state to open only."""
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)
    merged = replace(
        load_zammad_mcp_settings(),
        laptop_specialist_owner="",
    )
    with patch("zammad_mcp.server.zammad_mcp_settings.ZAMMAD_MCP_SETTINGS", merged):
        mark_as_agent_managed_laptop_refresh(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == ["zammad_add_ticket_tag", "zammad_update_ticket"]
    assert mock_basher.call_args_list[1][0][1] == {
        "ticket_id": 100,
        "state": "open",
    }


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_mark_as_general_agent_managed_splits_state_then_owner(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)
    mark_as_general_agent_managed(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == [
        "zammad_add_ticket_tag",
        "zammad_update_ticket",
        "zammad_update_ticket",
    ]
    assert mock_basher.call_args_list[0][0][1] == {
        "ticket_id": 100,
        "tag": "agent-managed-general-support",
    }
    assert mock_basher.call_args_list[1][0][1] == {
        "ticket_id": 100,
        "state": "open",
    }
    assert mock_basher.call_args_list[2][0][1] == {
        "ticket_id": 100,
        "owner": "agent.general@example.com",
    }


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_close_ticket(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)

    result = close(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == ["zammad_add_ticket_tag", "zammad_update_ticket"]
    assert mock_basher.call_args_list[0][0][1] == {
        "ticket_id": 100,
        "tag": "closed-by-ai-agent",
    }
    assert mock_basher.call_args_list[1][0][1] == {
        "ticket_id": 100,
        "state": "closed",
    }
    assert "100" in result
    assert "closed" in result.lower()


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_close_ignores_env_when_authoritative_user_id_header_missing(
    mock_assert: Mock, mock_basher: Mock
) -> None:
    """Identity comes from MCP headers only; env alone must not authorize."""
    mock_assert.return_value = 100
    ctx = MockContext({})
    with patch.dict(
        os.environ,
        {"AUTHORITATIVE_USER_ID": "nicole.braun@zammad.org-1"},
        clear=False,
    ):
        result = close(ctx)

    assert "AUTHORITATIVE_USER_ID" in result
    mock_assert.assert_not_called()
    mock_basher.assert_not_called()


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_escalate_for_human_review(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)

    result = escalate_for_human_review(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == [
        "zammad_add_ticket_tag",
        "zammad_update_ticket",
    ]
    upd = mock_basher.call_args_list[1][0][1]
    assert "state" not in upd
    assert upd["group"] == "escalated_laptop_refresh_tickets"
    assert upd["owner"] == "-"
    assert "100" in result
    assert "owner cleared" in result.lower()


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.fetch_zammad_customer_user_rest")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_send_to_manager_review_requires_manager_env(
    mock_assert: Mock,
    mock_fetch: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    mock_fetch.return_value = {"email": "alice@company.com", "manager_email": ""}
    ctx = MockContext(auth_headers)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ZAMMAD_MANAGER_EMAIL", None)

    result = send_to_manager_review(ctx)
    assert "manager_email" in result or "failed" in result.lower()
    names = [c[0][0] for c in mock_basher.call_args_list]
    assert "zammad_get_ticket" not in names
    assert "zammad_get_user" not in names


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.fetch_zammad_customer_user_rest")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_send_to_manager_review_ok(
    mock_assert: Mock,
    mock_fetch: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    mock_fetch.return_value = {"email": "alice@company.com", "manager_email": ""}
    mock_basher.return_value = "ok"
    ctx = MockContext(auth_headers)
    with (
        patch.dict(
            os.environ,
            {
                "ZAMMAD_MANAGER_EMAIL": "mgr@company.com",
                "ZAMMAD_URL": "https://zammad.example.com",
            },
        ),
        patch(
            "zammad_mcp.settings.ZAMMAD_MCP_SETTINGS",
            load_zammad_mcp_settings(),
        ),
    ):
        result = send_to_manager_review(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == ["zammad_add_ticket_tag", "zammad_update_ticket"]
    upd = next(
        c[0][1] for c in mock_basher.call_args_list if c[0][0] == "zammad_update_ticket"
    )
    assert upd["owner"] == "mgr@company.com"
    assert "group" not in upd
    assert "mgr@company.com" in result


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.fetch_zammad_customer_user_rest")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_send_to_manager_review_uses_customer_manager_field(
    mock_assert: Mock,
    mock_fetch: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    mock_fetch.return_value = {
        "email": "alice@company.com",
        "manager_email": "manager1@example.com",
    }
    mock_basher.return_value = "ok"
    ctx = MockContext(auth_headers)
    with patch.dict(os.environ, {"ZAMMAD_URL": "https://zammad.example.com"}):
        result = send_to_manager_review(ctx)

    upd = next(
        c[0][1] for c in mock_basher.call_args_list if c[0][0] == "zammad_update_ticket"
    )
    assert upd["owner"] == "manager1@example.com"
    assert "manager1@example.com" in result


@patch("zammad_mcp.server.call_basher_tool")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_route_to_human_managed_queue(
    mock_assert: Mock,
    mock_basher: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    ctx = MockContext(auth_headers)

    result = route_to_human_managed_queue(ctx)

    names = [c[0][0] for c in mock_basher.call_args_list]
    assert names == ["zammad_add_ticket_tag", "zammad_update_ticket"]
    assert mock_basher.call_args_list[0][0][1] == {
        "ticket_id": 100,
        "tag": "escalated-human-review",
    }
    upd = mock_basher.call_args_list[1][0][1]
    assert upd == {
        "ticket_id": 100,
        "group": "human_managed_tickets",
        "owner": "-",
    }
    assert "100" in result
    assert "owner cleared" in result.lower()


@patch("zammad_mcp.server.fetch_zammad_customer_user_rest")
@patch("zammad_mcp.server.assert_ticket_customer_matches_basher")
def test_get_employee_laptop_info_loads_user_via_rest(
    mock_assert: Mock,
    mock_fetch_rest: Mock,
    auth_headers: dict[str, str],
) -> None:
    mock_assert.return_value = 100
    laptop = {
        "name": "Alice Johnson",
        "location": "EMEA",
        "laptop_model": "ThinkPad X1",
        "serial_number": "SN-001",
        "purchase_date": "2020-06-15",
        "warranty_expiry": "2030-06-15",
    }
    mock_fetch_rest.return_value = {
        "email": "alice@company.com",
        "current_laptop": json.dumps(laptop),
    }
    ctx = MockContext(auth_headers)
    out = get_employee_laptop_info(ctx)
    mock_fetch_rest.assert_called_once_with(100)
    assert "Employee Name: Alice Johnson" in out
    assert "ThinkPad X1" in out
