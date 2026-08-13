"""Auto-detect per-message timeout based on test script type."""

import os
from pathlib import Path

_DEFAULT_CHAT_MESSAGE_TIMEOUT = 60
_TICKET_SCRIPT = "ticket-responses-request-mgr.py"
_TICKET_POLL_BUFFER = (
    60  # extra seconds on top of TRIGGER_POLL_TIMEOUT for slow agent turns
)


def calculate_message_timeout(test_script: str, explicit: int | None) -> int:
    """Return explicit timeout (seconds) if set, otherwise infer from test_script name.

    Args:
        test_script: Script name (e.g. "chat-responses-request-mgr.py").
        explicit: User-provided --message-timeout value, or None for auto-detect.

    Chat scripts default to 60s; ticket scripts default to TRIGGER_POLL_TIMEOUT + 60s.
    """
    if explicit is not None:
        return explicit
    if Path(test_script).name == _TICKET_SCRIPT:
        return int(os.environ.get("TRIGGER_POLL_TIMEOUT", "180")) + _TICKET_POLL_BUFFER
    return _DEFAULT_CHAT_MESSAGE_TIMEOUT
