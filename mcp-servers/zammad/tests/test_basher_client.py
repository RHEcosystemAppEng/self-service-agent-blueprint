"""Tests for Basher MCP helpers (ticket auth, user search)."""

import json
from typing import Any
from unittest.mock import Mock, patch

import pytest
from zammad_mcp.basher_client import (
    assert_ticket_customer_matches_basher,
    get_user_id_by_email,
)


@patch("zammad_mcp.basher_client.call_basher_tool")
def test_assert_ticket_customer_embedded_email_matches(mock_basher: Mock) -> None:
    mock_basher.return_value = json.dumps(
        {"customer": {"id": 5, "email": "alice@example.com"}}
    )
    assert assert_ticket_customer_matches_basher(1, "alice@example.com") == 5
    mock_basher.assert_called_once()


@patch("zammad_mcp.basher_client.call_basher_tool")
def test_assert_ticket_customer_customer_id_uses_user_search(
    mock_basher: Mock,
) -> None:
    def _side_effect(name: str, params: dict[str, Any]) -> str:
        if name == "zammad_get_ticket":
            return json.dumps({"customer_id": 9})
        if name == "zammad_search_users":
            return json.dumps(
                {"items": [{"id": 9, "email": "bob@example.com"}], "count": 1}
            )
        raise AssertionError(name)

    mock_basher.side_effect = _side_effect
    assert assert_ticket_customer_matches_basher(2, "bob@example.com") == 9
    assert mock_basher.call_count == 2


@patch("zammad_mcp.basher_client.call_basher_tool")
def test_get_user_id_by_email_matches_row(mock_basher: Mock) -> None:
    mock_basher.return_value = json.dumps(
        {
            "items": [
                {"id": 3, "email": "other@example.com"},
                {"id": 42, "email": "target@example.com"},
            ],
            "count": 2,
        }
    )
    assert get_user_id_by_email("target@example.com") == 42
    mock_basher.assert_called_once_with(
        "zammad_search_users",
        {
            "query": "target@example.com",
            "page": 1,
            "per_page": 25,
            "response_format": "json",
        },
    )


@patch("zammad_mcp.basher_client.call_basher_tool")
def test_get_user_id_by_email_raises_when_missing(mock_basher: Mock) -> None:
    mock_basher.return_value = json.dumps({"items": [{"id": 1, "email": "a@b.com"}]})
    with pytest.raises(ValueError, match="No Zammad user"):
        get_user_id_by_email("missing@example.com")
