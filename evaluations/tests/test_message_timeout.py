"""Tests for evaluation message-timeout resolution."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers.calculate_message_timeout import calculate_message_timeout


def test_chat_script_default() -> None:
    assert calculate_message_timeout("chat-responses-request-mgr.py", None) == 60


def test_chat_script_with_path() -> None:
    assert (
        calculate_message_timeout("/app/test/chat-responses-request-mgr.py", None) == 60
    )


def test_ticket_script_default() -> None:
    assert calculate_message_timeout("ticket-responses-request-mgr.py", None) == 240


def test_ticket_script_custom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIGGER_POLL_TIMEOUT", "200")
    assert calculate_message_timeout("ticket-responses-request-mgr.py", None) == 260


def test_explicit_overrides_auto() -> None:
    assert calculate_message_timeout("ticket-responses-request-mgr.py", 60) == 60
