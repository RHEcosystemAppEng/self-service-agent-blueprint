"""
Deterministic metric that validates every user turn receives an assistant reply.

This catches the production bug where ticket state changes but the user never sees
any agent reply — including close/escalate requests phrased in ways phrase matching
may miss (e.g. "Mark this as resolved").
"""

import re
from typing import Any, Optional

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case import ConversationalTestCase

_CLOSE_REQUEST_PHRASES = (
    "close the ticket",
    "close this ticket",
    "close my ticket",
    "close ticket",
    "closing the ticket",
    "closing this ticket",
    "please close",
    "close it",
    "close this",
    "ticket be closed",
    "ask to close",
)

# Catches morphological variants not listed above (e.g. "could you close the ticket").
_CLOSE_TICKET_PATTERN = re.compile(
    r"\bclos(?:e|es|ing|ed)\b(?:\s+\w+){0,4}\s+(?:the\s+)?ticket\b"
    r"|\bclos(?:e|es|ing)\b\s+it\b"
    r"|\bticket\b(?:\s+\w+){0,4}\s+be\s+closed\b",
    re.IGNORECASE,
)

_ESCALATE_REQUEST_PHRASES = (
    "escalate",
    "escalating",
    "escalation",
    "escalating to",
    "escalate to",
    "escalate this",
    "human to handle",
    "network specialist",
    "human review",
    "human assistance",
    "human agent",
    "speak to a human",
    "talk to a human",
    "to a human",
    "to a specialist",
)

# Catches morphological variants (e.g. "need escalating to", "I'd like escalating this to a human").
_ESCALATE_TICKET_PATTERN = re.compile(
    r"\bescalat(?:e|es|ing|ion)\b(?:\s+\w+){0,4}\s+(?:to\s+)?(?:a\s+)?(?:human|specialist|agent)\b"
    r"|\b(?:need|want|like|rather)\b(?:\s+\w+){0,4}\s+escalat(?:e|es|ing|ion)\b",
    re.IGNORECASE,
)

# Exclude negated formulations (e.g. "Please don't escalate this to a network specialist").
_CLOSE_NEGATION_PATTERN = re.compile(
    r"(?:don'?t|do not|shouldn'?t|should not|won'?t|will not|never|without)\s+(?:\w+\s+){0,10}"
    r"(?:clos(?:e|es|ing)\b(?:\s+\w+){0,4}\s+(?:the\s+)?ticket\b|ticket\b(?:\s+\w+){0,4}\s+be\s+closed\b)"
    r"|\bnot\s+(?:\w+\s+){0,4}clos(?:e|es|ing)\b(?:\s+\w+){0,4}\s+(?:the\s+)?ticket\b",
    re.IGNORECASE,
)
_ESCALATE_NEGATION_PATTERN = re.compile(
    r"(?:don'?t|do not|shouldn'?t|should not|won'?t|will not|never|without)\s+(?:\w+\s+){0,10}"
    r"(?:escalat(?:e|es|ing|ion)\b|network specialist\b|human to handle\b|human assistance\b|"
    r"human agent\b|human review\b|speak to a human\b|talk to a human\b|to a specialist\b|to a human\b)"
    r"|\bnot\s+(?:\w+\s+){0,4}(?:escalat(?:e|es|ing|ion)\b|network specialist\b)",
    re.IGNORECASE,
)

# Exclude self-directed questions (e.g. "should I escalate?"), not agent-directed requests
# such as "Can you close the ticket?".
_CLOSE_QUESTION_PATTERN = re.compile(
    r"(?:should|could|would|can|may|might)\s+(?:I|we)\s+(?:\w+\s+){0,10}"
    r"(?:clos(?:e|es|ing)\b|ticket\b(?:\s+\w+){0,4}\s+be\s+closed\b)"
    r"|(?:should|could|would|can)\s+(?:the|this|my)\s+ticket\b(?:\s+\w+){0,4}\s+be\s+closed\b",
    re.IGNORECASE,
)
_ESCALATE_QUESTION_PATTERN = re.compile(
    r"(?:should|could|would|can|may|might)\s+(?:I|we)\s+(?:\w+\s+){0,10}"
    r"(?:escalat(?:e|es|ing|ion)\b|network specialist\b|human\b|specialist\b|agent\b)"
    r"|(?:should|could|would|can)\s+(?:the|this|my)\s+ticket\b(?:\s+\w+){0,4}\s+be\s+escalated\b",
    re.IGNORECASE,
)


def _is_excluded_request(content: str, action: str) -> bool:
    """Return True for negated or self-directed question formulations."""
    if action == "close":
        return bool(
            _CLOSE_NEGATION_PATTERN.search(content)
            or _CLOSE_QUESTION_PATTERN.search(content)
        )
    return bool(
        _ESCALATE_NEGATION_PATTERN.search(content)
        or _ESCALATE_QUESTION_PATTERN.search(content)
    )


def _user_requests_close_or_escalate(content: str) -> Optional[str]:
    lower = content.lower()
    if any(
        phrase in lower for phrase in _CLOSE_REQUEST_PHRASES
    ) or _CLOSE_TICKET_PATTERN.search(content):
        if not _is_excluded_request(content, "close"):
            return "close"
    if any(
        phrase in lower for phrase in _ESCALATE_REQUEST_PHRASES
    ) or _ESCALATE_TICKET_PATTERN.search(content):
        if not _is_excluded_request(content, "escalate"):
            return "escalate"
    return None


class CloseOrEscalationConfirmationDeterministicEval(BaseConversationalMetric):
    """
    Deterministic metric: every user turn must be followed by an assistant reply.

    Close/escalate phrase matching is best-effort and used only to label failures
    (close / escalate / other). It does not gate whether the check runs.
    """

    def __init__(
        self,
        name: str = "Close or Escalation Confirmation — deterministic",
        threshold: float = 1.0,
        include_reason: bool = True,
        async_mode: bool = True,
        **kwargs: Any,
    ) -> None:
        self.threshold = threshold
        self.name = name
        self.include_reason = include_reason
        self.async_mode = async_mode

    def measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        turns = test_case.turns
        failures: list[str] = []

        for i, turn in enumerate(turns):
            if turn.role != "user":
                continue

            next_turn = turns[i + 1] if i + 1 < len(turns) else None
            if next_turn and next_turn.role == "assistant":
                continue

            request_type = _user_requests_close_or_escalate(turn.content) or "other"
            failures.append(
                f"User message ({request_type} request) had no assistant reply following"
            )

        self.score = 0.0 if failures else 1.0
        self.reason = (
            "; ".join(failures)
            if failures
            else "All user turns received an assistant reply"
        )
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        if self.error is not None:
            self.success = False
        elif self.score is None:
            self.success = False
        else:
            self.success = self.score >= self.threshold
        return self.success

    @property
    def __name__(self) -> str:
        return self.name
