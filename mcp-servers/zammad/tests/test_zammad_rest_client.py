"""Tests for Zammad REST client helpers."""

from dataclasses import replace
from unittest.mock import MagicMock, Mock, patch

import pytest
from zammad_mcp.settings import ZAMMAD_MCP_SETTINGS
from zammad_mcp.zammad_rest_client import (
    ZammadRestClient,
    _get_zammad_rest_client,
    fetch_zammad_customer_user_rest,
)


def test_zammad_rest_client_init_trims_whitespace_and_slash() -> None:
    c = ZammadRestClient("  http://host:8080/  ", "tok")
    assert c._base == "http://host:8080"


@patch("zammad_mcp.zammad_rest_client.ZammadRestClient")
def test_get_zammad_rest_client_uses_rest_base_url(mock_client_class: Mock) -> None:
    with patch(
        "zammad_mcp.zammad_rest_client.ZAMMAD_MCP_SETTINGS",
        replace(
            ZAMMAD_MCP_SETTINGS,
            zammad_rest_base_url="http://zammad-nginx.test-it-ssa.svc.cluster.local:8080",
        ),
    ):
        _get_zammad_rest_client("secret-token")
    mock_client_class.assert_called_once_with(
        base_url="http://zammad-nginx.test-it-ssa.svc.cluster.local:8080",
        http_token="secret-token",
    )


def test_get_zammad_rest_client_requires_url() -> None:
    with (
        patch(
            "zammad_mcp.zammad_rest_client.ZAMMAD_MCP_SETTINGS",
            replace(ZAMMAD_MCP_SETTINGS, zammad_rest_base_url=""),
        ),
        pytest.raises(ValueError, match="ZAMMAD_URL"),
    ):
        _get_zammad_rest_client("secret-token")


@patch("zammad_mcp.zammad_rest_client._get_zammad_rest_client")
def test_fetch_zammad_customer_user_rest(mock_client_factory: Mock) -> None:
    mock_client = MagicMock()
    mock_client.get_user.return_value = {"id": 3, "manager_email": "m@x.com"}
    mock_client_factory.return_value = mock_client
    out = fetch_zammad_customer_user_rest(3)
    assert out["manager_email"] == "m@x.com"
    mock_client.get_user.assert_called_once_with(3)
