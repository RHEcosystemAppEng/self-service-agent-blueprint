"""Flow configuration for ticket_laptop_refresh evaluation."""

from typing import List

FLOW_NAME: str = "ticket_laptop_refresh"
DEFAULT_TEST_SCRIPT: str = "chat-responses-request-mgr.py"
DEFAULT_RESET_CONVERSATION: bool = True
DEFAULT_SKIP_INITIAL_MESSAGE: bool = True
KNOWLEDGE_BASE_DIRS: List[str] = ["laptop-refresh"]
INCLUDE_SNOW_DATA: bool = True

CHATBOT_ROLE: str = """You are an IT Support Agent specializing in hardware replacement.

Your responsibilities:
1. Determine if the authenticated user's laptop is eligible for replacement based on company policy
2. Clearly communicate the eligibility status and policy reasons to the user
3. If the user is NOT eligible:
   - Inform them of their ineligibility with the policy reason (e.g., laptop age)
   - Provide clear, factual information that proceeding may require additional approvals or be rejected
   - Allow them to continue with the laptop selection process if they choose to
4. Guide the user through laptop selection
5. After the user selects a laptop, ALWAYS ask for explicit confirmation before sending the ticket to their manager)
6. Only forward the ticket to the users manager AFTER the user confirms they want to proceed
8. Maintain a professional, helpful, and informative tone throughout

Note: Providing clear, factual information about potential rejection or additional approvals is sufficient. You do not need to be overly cautionary or repeatedly emphasize warnings. Always confirm with the user before creating tickets."""


_USER_DESCRIPTION = (
    "An employee responding to comments on their IT support ticket in a ticketing system. "
    "Their messages are brief and direct, as typical ticket comments — for example: 'requesting a laptop refresh', "
    "'please show me the options', 'option 3', 'yes proceed' — not conversational chat messages. "
    "When selecting from a numbered list of options, the employee selects option {option_number} from the list. "
    "The employee responds directly to the agent's most recent question without asking for confirmation "
    "of information that has already been provided."
)

_SCENARIOS = [
    (
        "An employee has submitted a ticket requesting a laptop refresh. The employee opens the conversation by "
        "requesting a laptop refresh in a short, direct comment. The agent replies with the employee's current laptop "
        "details and their eligibility status based on company policy. "
        "The employee responds with short, direct ticket comments and ONLY reacts to what the agent has already said — "
        "they never select a laptop or take an action before the agent has explicitly presented that option. "
        "If the agent says they ARE eligible and presents a list of laptops, the employee selects one from the list "
        "(specifically option {option_number}), "
        "then confirms when the agent asks before the ticket is sent to their manager for approval. "
        "If the agent says they are NOT eligible, the employee chooses to escalate the ticket to request an exception.",
        "The ticket is either routed to the user's manager for approval (if eligible) or escalated for an exception (if not eligible).",
        _USER_DESCRIPTION,
    ),
    (
        "An employee has submitted a ticket requesting a laptop refresh. The employee opens the conversation by "
        "requesting a laptop refresh in a short, direct comment. The agent replies with the employee's current laptop "
        "details and their eligibility status based on company policy. "
        "The employee responds with short, direct ticket comments and ONLY reacts to what the agent has already said — "
        "they never select a laptop or take an action before the agent has explicitly presented that option. "
        "If the agent says they ARE eligible and presents a list of laptops, the employee selects one from the list "
        "(specifically option {option_number}), "
        "then confirms when the agent asks before the ticket is sent to their manager for approval. "
        "If the agent says they are NOT eligible, the employee chooses to close the ticket.",
        "The ticket is either routed to the user's manager for approval (if eligible) or closed (if not eligible).",
        _USER_DESCRIPTION,
    ),
]


def get_scenario(use_structured_output: bool) -> list[tuple[str, str, str]]:
    """Return a list of (scenario, expected_outcome, user_description) tuples for conversation generation."""
    return _SCENARIOS
