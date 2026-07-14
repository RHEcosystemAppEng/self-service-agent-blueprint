"""Tests for evaluation message-timeout resolution."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers.message_timeout import (
    DEFAULT_CHAT_MESSAGE_TIMEOUT,
    TICKET_HARNESS_POLL_BUFFER_SEC,
    default_message_timeout_for_script,
    resolve_message_timeout,
    ticket_harness_poll_timeout,
)


def test_default_for_chat_script() -> None:
    assert default_message_timeout_for_script("chat-responses-request-mgr.py") == 60
    assert (
        default_message_timeout_for_script("/app/test/chat-responses-request-mgr.py")
        == 60
    )


def test_default_for_ticket_script() -> None:
    expected = int(ticket_harness_poll_timeout() + TICKET_HARNESS_POLL_BUFFER_SEC)
    assert (
        default_message_timeout_for_script("ticket-responses-request-mgr.py")
        == expected
    )


def test_resolve_honors_explicit_timeout() -> None:
    assert resolve_message_timeout("ticket-responses-request-mgr.py", 60) == 60


def test_resolve_auto_for_ticket_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIGGER_POLL_TIMEOUT", "200")
    assert resolve_message_timeout("ticket-responses-request-mgr.py", None) == 260


def test_resolve_auto_for_chat_script() -> None:
    assert (
        resolve_message_timeout("chat-responses-request-mgr.py", None)
        == DEFAULT_CHAT_MESSAGE_TIMEOUT
    )
