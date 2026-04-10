"""DeepEval metrics for ticket_unrelated flow."""

from typing import Any, List, Optional

from deepeval.metrics import ConversationalGEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import TurnParams


def get_metrics(
    custom_model: Optional[DeepEvalBaseLLM] = None,
    validate_full_laptop_details: bool = True,
) -> List[Any]:
    """Create evaluation metrics for the ticket_unrelated flow."""

    metrics = [
        ConversationalGEval(
            name="Scope Refusal",
            threshold=0.9,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the agent correctly refused to help with the user's unrelated request.",
                "The agent MUST:",
                "  1. Clearly communicate that it cannot help with the user's request",
                "  2. Not attempt to answer or partially answer the unrelated question",
                "PASS if the agent clearly declines the out-of-scope request.",
                "FAIL if the agent attempts to answer the unrelated question or provides any relevant information about it.",
            ],
        ),
        ConversationalGEval(
            name="Escalation Confirmation",
            threshold=0.9,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the agent informed the user that their ticket has been escalated for human review.",
                "PASS if the agent explicitly states the ticket has been escalated for human review (or similar — e.g. 'routed to human review', 'passed to a human agent').",
                "FAIL if the agent refuses without mentioning escalation, or if the conversation ends without the user being told what will happen next.",
            ],
        ),
        ConversationalGEval(
            name="Conversation Brevity",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the conversation ends promptly after the agent declines and escalates.",
                "For an unrelated request the correct flow is: user asks → agent declines and escalates → conversation ends.",
                "PASS if the conversation completes within 2 agent turns.",
                "FAIL if the agent continues the conversation unnecessarily after declining and escalating.",
            ],
        ),
        ConversationalGEval(
            name="User Experience",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the agent is polite and professional when escalating the out-of-scope request.",
                "IMPORTANT: This is a backend ticket-routing agent. It is NOT expected to address the user's specific request or provide domain expertise.",
                "The correct and complete agent response is simply to inform the user their ticket has been escalated for human review.",
                "Do NOT penalise the agent for failing to help with the user's topic (e.g. password resets, software installs) — that is intentional.",
                "PASS if the agent's escalation message is polite, professional, and clearly tells the user what will happen next.",
                "FAIL only if the agent is rude, dismissive, confusing, or provides no information about what will happen to the ticket.",
            ],
        ),
        ConversationalGEval(
            name="No errors reported by agent",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "This metric ONLY checks for explicit technical/system errors reported by the agent.",
                "FAIL ONLY if the agent explicitly reports a technical or system error such as:",
                "  - Any HTTP error code",
                "  - 'I could not complete this request due to an error'",
                "  - 'An error occurred while processing your request'",
                "  - 'Something went wrong' or 'I encountered an error'",
                "  - Tool call failures or stack traces visible in the response",
                "PASS if the agent responds normally even if it simply declines to help.",
            ],
        ),
    ]

    return metrics
