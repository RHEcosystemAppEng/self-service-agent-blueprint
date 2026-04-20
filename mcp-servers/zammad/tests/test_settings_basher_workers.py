"""Tests for ZAMMAD_BASHER_MCP_MAX_WORKERS."""

import os
from unittest.mock import patch

import pytest
from zammad_mcp.settings import load_zammad_mcp_settings


def _minimal_env(**extra: str) -> dict[str, str]:
    return {
        "ZAMMAD_URL": "https://z.example",
        "ZAMMAD_HTTP_TOKEN": "token",
        **extra,
    }


def test_basher_mcp_max_workers_default() -> None:
    with patch.dict(os.environ, _minimal_env(), clear=True):
        s = load_zammad_mcp_settings()
    assert s.basher_mcp_max_workers == 8


def test_basher_mcp_max_workers_custom() -> None:
    with patch.dict(
        os.environ,
        _minimal_env(ZAMMAD_BASHER_MCP_MAX_WORKERS="3"),
        clear=True,
    ):
        s = load_zammad_mcp_settings()
    assert s.basher_mcp_max_workers == 3


def test_basher_mcp_max_workers_clamped() -> None:
    with patch.dict(
        os.environ,
        _minimal_env(ZAMMAD_BASHER_MCP_MAX_WORKERS="0"),
        clear=True,
    ):
        assert load_zammad_mcp_settings().basher_mcp_max_workers == 1
    with patch.dict(
        os.environ,
        _minimal_env(ZAMMAD_BASHER_MCP_MAX_WORKERS="999"),
        clear=True,
    ):
        assert load_zammad_mcp_settings().basher_mcp_max_workers == 128


def test_basher_mcp_max_workers_invalid() -> None:
    with patch.dict(
        os.environ,
        _minimal_env(ZAMMAD_BASHER_MCP_MAX_WORKERS="nope"),
        clear=True,
    ):
        with pytest.raises(ValueError, match="ZAMMAD_BASHER_MCP_MAX_WORKERS"):
            load_zammad_mcp_settings()
