"""
Deterministic metric that validates every user turn receives an assistant reply.

This catches the production bug where ticket state changes but the user never sees
any agent reply after their message.
"""

from typing import Any

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case import ConversationalTestCase


class UserTurnAssistantReplyDeterministicEval(BaseConversationalMetric):
    """
    Deterministic metric: every user turn must be followed by an assistant reply.
    """

    def __init__(
        self,
        name: str = "User Turn Assistant Reply — deterministic",
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

            failures.append("User message had no assistant reply following")

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
