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
            name="Helpfulness",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the agent makes a genuine attempt to help the user with their IT question before any escalation or closure.",
                "The agent is a general support agent with no specialist tools — it answers based on general IT knowledge.",
                "PASS if the agent engages with the user's question and provides relevant information or guidance at any point in the conversation.",
                "PASS if the agent escalates or closes the ticket in response to an explicit user request, even if no further troubleshooting is offered at that point — the agent has already fulfilled its helpfulness obligation.",
                "FAIL if the agent escalates or closes the ticket on its very first response without making any attempt to engage with the user's question.",
                "FAIL if the agent refuses to answer or ignores the user's question entirely.",
            ],
        ),
        ConversationalGEval(
            name="Ticket Resolution",
            threshold=0.9,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the conversation ends with the ticket being either closed or escalated.",
                "PASS if the agent explicitly confirms one of:",
                "  - The ticket has been closed (e.g. 'Your ticket has been closed')",
                "  - The ticket has been escalated for human review (e.g. 'Your ticket has been escalated for human review')",
                "FAIL if the conversation ends without either of these confirmations.",
            ],
        ),
        ConversationalGEval(
            name="User-Initiated Close or Escalation",
            threshold=0.9,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate whether the ticket is only closed or escalated after the user explicitly requests it.",
                "The agent must NOT proactively close or escalate the ticket on its own.",
                "PASS if the close or escalation clearly follows an explicit user request to close or escalate.",
                "FAIL if the agent closes or escalates the ticket without the user asking for it.",
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
                "PASS if the agent responds normally even if it cannot fully resolve the user's issue.",
            ],
        ),
    ]

    return metrics
