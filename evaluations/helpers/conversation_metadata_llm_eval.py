"""
A custom LLM-based conversational metric for validating conversation metadata transitions.

This metric uses an LLM to judge whether actual_conversation_metadata on assistant
turns follows valid estimated metadata values based on flow-specific state machine rules.

It is designed for generated conversations that have actual metadata but no
expected metadata. Skips when expected metadata exists (since deterministic metric handles it).

Usage:
    from helpers.conversation_metadata_llm_eval import ConversationMetadataLLMEval

    metric = ConversationMetadataLLMEval(
        name="Correct conversation metadata — LLM (generated)",
        threshold=1.0,
        model=custom_model,
        evaluation_steps=[...],  # flow-specific state machine rules
    )
"""

import json
import logging
from typing import Any, List, Optional

from deepeval.metrics import BaseConversationalMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, Turn

logger = logging.getLogger(__name__)


class ConversationMetadataLLMEval(BaseConversationalMetric):
    """
    LLM-based metric that validates generated conversation metadata transitions.

    For each assistant turn with actual_conversation_metadata, uses an LLM to
    judge whether the state transitions follow the flow's state machine rules.

    Scores 1.0 if all transitions are valid, 0.0 if any transition violates the rules.
    Skips (scores 1.0) if expected metadata exists, no actual metadata, or no model configured.
    """

    def __init__(
        self,
        name: str = "Correct conversation metadata — LLM (generated)",
        threshold: float = 1.0,
        include_reason: bool = True,
        async_mode: bool = True,
        model: Optional[DeepEvalBaseLLM] = None,
        evaluation_steps: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        if evaluation_steps is not None and len(evaluation_steps) == 0:
            raise ValueError("'evaluation_steps' must not be an empty list.")

        self.threshold = threshold
        self.name = name
        self.include_reason = include_reason
        self.async_mode = async_mode
        self.model = model
        self.evaluation_steps = evaluation_steps

    def measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        turns = test_case.turns

        has_expected_metadata = any(
            turn.role == "user" and turn.additional_metadata is not None
            for turn in turns
        )
        has_actual_metadata = any(
            turn.role == "assistant" and turn.additional_metadata is not None
            for turn in turns
        )

        # Skip — deterministic metric handles predefined conversations
        if has_expected_metadata:
            self.score = 1.0
            self.success = True
            self.reason = "Skipped — expected metadata present (deterministic metric handles this)"
            return self.score

        # Skip — no actual metadata or no model/evaluation_steps configured
        if (
            not has_actual_metadata
            or self.model is None
            or self.evaluation_steps is None
        ):
            self.score = 1.0
            self.success = True
            self.reason = (
                "No conversation metadata to evaluate"
                if not has_actual_metadata
                else f"Actual metadata present but no {'model' if self.model is None else 'evaluation_steps'} configured"
            )
            return self.score

        # Build conversation text with metadata tags on assistant turns
        conversation_lines: List[str] = []
        for turn in turns:
            metadata_str = ""
            if turn.role == "assistant" and turn.additional_metadata:
                meta = turn.additional_metadata
                metadata_str = (
                    f" [actual_conversation_metadata: "
                    f"state={meta.get('state')}, "
                    f"owner={meta.get('owner')}, "
                    f"group={meta.get('group')}]"
                )
            conversation_lines.append(f"{turn.role}: {turn.content}{metadata_str}")

        steps = "\n".join(self.evaluation_steps)
        prompt = (
            f"{steps}\n\n"
            f"Conversation:\n" + "\n".join(conversation_lines) + "\n\n"
            'Respond with ONLY a JSON object: {"score": <integer 0-10>, '
            '"reason": "<brief explanation>"}'
        )

        try:
            response = self.model.generate(prompt)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(cleaned)
            self.score = float(result.get("score", 0)) / 10
            self.reason = f"LLM evaluation: {result.get('reason', 'no reason')}"
            logger.info(
                f"LLM metadata evaluation: score={self.score}, reason={self.reason}"
            )
        except Exception as e:
            logger.warning(f"LLM metadata evaluation failed: {e}")
            self.score = 0.0
            self.reason = f"LLM evaluation failed: {e}"

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
