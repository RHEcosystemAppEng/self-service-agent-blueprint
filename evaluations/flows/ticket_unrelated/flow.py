"""Flow configuration for ticket_unrelated evaluation."""

from typing import List

FLOW_NAME: str = "ticket_unrelated"
DEFAULT_TEST_SCRIPT: str = "ticket-responses-request-mgr.py"
DEFAULT_RESET_CONVERSATION: bool = False
DEFAULT_SKIP_INITIAL_MESSAGE: bool = True
DEFAULT_INITIAL_MESSAGE: str = "requesting a laptop refresh"
DEFAULT_TICKET_TITLE: str = "non laptop refresh request"
DEFAULT_MAX_TURNS: int = 1  # One user message → one agent response → done
KNOWLEDGE_BASE_DIRS: List[str] = ["laptop-refresh"]
INCLUDE_SNOW_DATA: bool = True

CHATBOT_ROLE: str = """You are an IT Support Agent specializing in hardware replacement (laptop refresh).
You only handle laptop refresh requests. For any other topic you politely inform the user
you cannot help and that their ticket has been escalated for human review."""

_USER_DESCRIPTION = (
    "An employee who has submitted a ticket on an unrelated topic (not laptop refresh). "
    "Their messages are brief and direct, as typical ticket comments. "
    "The employee asks their unrelated question. Once the agent responds that it cannot help "
    "and that the ticket has been escalated, the employee does not reply — the conversation ends."
)

_SCENARIOS = [
    (
        "An employee has submitted a support ticket asking about something completely unrelated "
        "to laptop refresh — for example a password reset, a software installation request, "
        "a question about office supplies, or a general IT question. "
        "The employee sends a single message with their unrelated request. "
        "The agent responds that it cannot help with that topic and that the ticket has been "
        "escalated for human review. "
        "After receiving that response the employee does NOT reply — the conversation is over.",
        "The agent has explicitly stated it cannot help with the request AND has confirmed the "
        "ticket has been escalated for human review. The conversation is complete and requires "
        "no further user response.",
        _USER_DESCRIPTION,
    ),
]


def get_scenario(use_structured_output: bool) -> list[tuple[str, str, str]]:
    """Return a list of (scenario, expected_outcome, user_description) tuples for conversation generation."""
    return _SCENARIOS
