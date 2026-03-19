"""Flow configuration for ticket_laptop_refresh evaluation."""

from typing import List

FLOW_NAME: str = "ticket_laptop_refresh"
DEFAULT_TEST_SCRIPT: str = "chat-responses-request-mgr.py"
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


def get_scenario(use_structured_output: bool) -> tuple[tuple[str, str, str], str, str]:
    """Return (scenario, expected_outcome, user_description) for conversation generation."""
    expected_outcome = "They get a Service now ticket number for their refresh request"

    scenario = (
        "A ticket is created by the user asking to refresh their laptop. An agents responsds on the ticket with their current laptop information and their elligibiblity for a fresh based on the company policy",
        "If the user is elligible the agent will provide a list of options, the user selects one and the agent will ask if they would like the ticket to be sent to their manager for approval.",
        "If the user is not elligible the agent will ask if the user would like to close or escalate the ticket.",
    )
    user_description = "An employee interacting with an IT self-service agent through a ticket in a ticketing system."

    return scenario, expected_outcome, user_description
