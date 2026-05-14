"""
A custom deterministic conversational metric for comparing expected vs actual conversation metadata.

This metric compares metadata stored in Turn.additional_metadata between
paired user/assistant turns. It is fully deterministic — no LLM is used.

User turns hold expected metadata, assistant turns hold actual metadata.
The metric compares all fields in each pair and reports mismatches.

Usage:
    from helpers.conversation_metadata_eval import ConversationMetadataEval

    metric = ConversationMetadataEval(
        name="Correct conversation metadata",
        threshold=1.0,
    )
"""

from typing import Any, List

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case import ConversationalTestCase


class ConversationMetadataEval(BaseConversationalMetric):
    """
    Deterministic metric that compares expected vs actual metadata per turn pair.

    For each user turn with additional_metadata (expected), finds the immediately
    following assistant turn's additional_metadata (actual) and compares all fields.

    Scores 1.0 if all pairs match, 0.0 if any pair has a mismatch.
    Skips (scores 1.0) if no turn has additional_metadata.
    """

    def __init__(
        self,
        name: str = "Correct conversation metadata",
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
        mismatches: List[str] = []
        pair_count = 0

        for i, turn in enumerate(turns):
            if turn.role != "user" or turn.additional_metadata is None:
                continue

            expected = turn.additional_metadata
            pair_count += 1
            next_turn = turns[i + 1] if i + 1 < len(turns) else None

            if not next_turn or next_turn.role != "assistant":
                mismatches.append(
                    f"pair {pair_count}: no assistant turn following user turn"
                )
                continue

            actual = next_turn.additional_metadata
            if actual is None:
                mismatches.append(
                    f"pair {pair_count}: assistant turn has no actual metadata"
                )
                continue

            for key in expected.keys() | actual.keys():
                if expected.get(key) != actual.get(key):
                    mismatches.append(
                        f"pair {pair_count}: {key} expected='{expected.get(key)}' actual='{actual.get(key)}'"
                    )

        self.score = 0.0 if mismatches else 1.0
        self.reason = (
            "No conversation metadata to evaluate"
            if pair_count == 0
            else (
                f"All {pair_count} metadata pair(s) match"
                if not mismatches
                else f"Metadata mismatch: {'; '.join(mismatches)}"
            )
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
