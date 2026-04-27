"""Flow configuration for ticket_unrelated evaluation."""

from typing import List

FLOW_NAME: str = "ticket_unrelated"
DEFAULT_TEST_SCRIPT: str = "ticket-responses-request-mgr.py"
DEFAULT_RESET_CONVERSATION: bool = False
DEFAULT_SKIP_INITIAL_MESSAGE: bool = True
DEFAULT_INITIAL_MESSAGE: str = "requesting a laptop refresh"
DEFAULT_TICKET_TITLE: str = "non laptop refresh request"
DEFAULT_MAX_TURNS: int = 10
KNOWLEDGE_BASE_DIRS: List[str] = []
INCLUDE_SNOW_DATA: bool = False

CHATBOT_ROLE: str = """You are a General IT Support Agent that handles support tickets on any topic.

Your responsibilities:
1. Greet the user and let them know you are a general support agent that can answer questions based on general knowledge
2. Try to answer the user's question or address their request as helpfully as possible
3. Let the user know they can ask follow-up questions at any time
4. Inform the user they can close the ticket if their issue is resolved, or escalate to a human agent if they need further assistance
5. When the user asks to close the ticket, confirm the ticket has been closed — the conversation ends here. No further responses from the user are expected after this message
6. When the user asks to escalate, confirm the ticket has been escalated for human review — the conversation ends here. No further respeonse are expected from the user after this message
7. Maintain a professional, helpful tone throughout"""

_SCENARIOS = [
    (
        "An employee has submitted a support ticket asking a general IT support question unrelated to laptop hardware. "
        "The employee opens the conversation by directly stating their specific IT question or issue in a short, direct comment — no generic greetings. "
        "The agent attempts to answer their question. "
        "The employe DOES NOT ask for the ticket to be escalated"
        "The employee asks up to four follow-up questions and then asks that the ticket be closed "
        "STOP: the employee sends no further messages after asking to close — the conversation is complete.",
        "The agent has confirmed the ticket is closed with the message 'Your ticket has been closed'.",
        "An employee responding to comments on their IT support ticket. Their messages are brief and direct.",
    ),
    (
        "An employee has submitted a support ticket asking a general IT support question unrelated to laptop hardware. "
        "The employee opens the conversation by directly stating their specific IT question or issue in a short, direct comment — no generic greetings. "
        "The agent attempts to answer their question. "
        "The employe DOES NOT ask for the ticket to be closed"
        "The employee may ask one or two brief follow-up questions. "
        "The employee decides they need further human assistance and sends a single message asking to escalate the ticket. "
        "STOP: the employee sends no further messages after asking to escalate — the conversation is complete.",
        "The agent has confirmed the ticket escalation with the message 'Your ticket has been escalated for human review'.",
        "An employee responding to comments on their IT support ticket. Their messages are brief and direct.",
    ),
]


def get_scenario(use_structured_output: bool) -> list[tuple[str, str, str]]:
    """Return a list of (scenario, expected_outcome, user_description) tuples for conversation generation."""
    return _SCENARIOS
