"""Resolve per-message timeouts for evaluation harness subprocesses."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CHAT_MESSAGE_TIMEOUT = 60
TICKET_RESPONSES_SCRIPT = "ticket-responses-request-mgr.py"
# Room for TICKET_STATUS and slow agent turns after Zammad poll completes.
TICKET_HARNESS_POLL_BUFFER_SEC = 60


def ticket_harness_poll_timeout() -> int:
    """Match test/ticket-responses-request-mgr.py TRIGGER_POLL_TIMEOUT default."""
    return int(os.environ.get("TRIGGER_POLL_TIMEOUT", "180"))


def default_message_timeout_for_script(test_script: str) -> int:
    """Infer a safe per-message timeout from the harness script name."""
    if Path(test_script).name == TICKET_RESPONSES_SCRIPT:
        return ticket_harness_poll_timeout() + TICKET_HARNESS_POLL_BUFFER_SEC
    return DEFAULT_CHAT_MESSAGE_TIMEOUT


def resolve_message_timeout(test_script: str, explicit: int | None) -> int:
    """Return explicit timeout when set, otherwise script-aware default."""
    if explicit is not None:
        return explicit
    return default_message_timeout_for_script(test_script)
