"""Tests for Zammad HTTP token (loaded settings)."""

from dataclasses import replace
from unittest.mock import patch

import pytest
from zammad_mcp.settings import ZAMMAD_MCP_SETTINGS
from zammad_mcp.zammad_rest_client import _get_zammad_rest_client


def test_token_from_env() -> None:
    with patch(
        "zammad_mcp.zammad_rest_client.ZAMMAD_MCP_SETTINGS",
        replace(
            ZAMMAD_MCP_SETTINGS,
            zammad_http_token="pod-secret",
            zammad_rest_base_url="https://z.example",
        ),
    ):
        client = _get_zammad_rest_client()
    assert client._headers["Authorization"] == "Token token=pod-secret"


def test_missing_token_raises() -> None:
    with (
        patch(
            "zammad_mcp.zammad_rest_client.ZAMMAD_MCP_SETTINGS",
            replace(
                ZAMMAD_MCP_SETTINGS,
                zammad_http_token="",
                zammad_rest_base_url="https://z.example",
            ),
        ),
        pytest.raises(ValueError, match="ZAMMAD_HTTP_TOKEN is not set"),
    ):
        _get_zammad_rest_client()
