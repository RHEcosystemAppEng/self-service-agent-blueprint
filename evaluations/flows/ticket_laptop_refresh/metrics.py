#!/usr/bin/env python3
"""
DeepEval metrics for ticket_laptop_refresh flow.

Initially identical to the default chat-laptop-refresh metrics.
Modify this file independently to tailor evaluations for this flow.
"""

from typing import Any, List, Optional

from deepeval.metrics import ConversationalGEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, TurnParams
from helpers.load_conversation_context import load_default_context

# Context directory for this flow (populated at eval time by copy_flow_context).
# Path is relative to the evaluations/ working directory.
_FLOW_CONTEXT_DIR = "flows/ticket_laptop_refresh/context"


class RetryableConversationalGEval(ConversationalGEval):
    """
    A wrapper around ConversationalGEval that retries evaluation on failure.

    If the metric fails (score < threshold), it runs the evaluation a second time
    and uses the result from the second run.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retry_performed = False

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        """Async measure with retry logic."""
        self.retry_performed = False

        await super().a_measure(test_case, *args, **kwargs)

        if (
            self.score is not None
            and self.threshold is not None
            and self.score < self.threshold
        ):
            first_score = self.score
            first_reason = self.reason

            self.score = None
            self.reason = None
            self.success = None

            await super().a_measure(test_case, *args, **kwargs)

            self.retry_performed = True

            if self.reason:
                self.reason = f"[RETRY: 1st={first_score:.2f}] {self.reason}"

        return self.score if self.score is not None else 0.0


def get_metrics(
    custom_model: Optional[DeepEvalBaseLLM] = None,
    validate_full_laptop_details: bool = True,
) -> List[Any]:
    """
    Create evaluation metrics for the ticket_laptop_refresh flow.

    Initially identical to the default chat-laptop-refresh metrics.
    """
    default_context = load_default_context(context_dir=_FLOW_CONTEXT_DIR)

    metrics = [
        ConversationalGEval(
            name="Turn Relevancy",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if each assistant response is relevant to the user's message and conversation context.",
                "Only mark messages as irrelevant if they:",
                "  - Completely ignore the user's question or request",
                "  - Provide unrelated information",
                "  - Fail to address the user's actual need",
                "CRITICAL: When a user asks an out-of-scope question (e.g., password reset, monitor issue, software problem), a specialist agent that (a) states it can only help with laptop refresh AND (b) offers to escalate or redirect — is FULLY addressing the user's need within its role. This response is 100% RELEVANT. Do NOT mark it as irrelevant or partially irrelevant. Do NOT penalize for not solving the out-of-scope request directly.",
                "Do NOT mark as irrelevant:",
                "  - Specialist agent responses that stay within their scope",
                "  - Asking if the user would like to escalate for out-of-scope questions",
                "  - Repeating scope boundaries across multiple out-of-scope questions — this is correct behavior, not irrelevance",
            ],
        ),
        ConversationalGEval(
            name="Role Adherence",
            threshold=0.5,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if agents adhere to their assigned roles throughout the conversation.",
                "",
                "Agent role expectations:",
                "  - Laptop Refresh Specialist: Checks eligibility, presents options, escalates closes or assigns tickets to users manager",
                "",
                "Role adherence is CORRECT when:",
                "  - Specialist handles laptop tasks appropriately",
                "",
                "Role adherence FAILS only when:",
                "  - A specialist tries to handle requests outside their scope",
                "  - An agent provides responses completely inconsistent with any valid role",
                "  - CRITICAL FAILURE: The Laptop Refresh Specialist offers to CREATE a ticket (e.g., 'Would you like to proceed with the creation of a ServiceNow ticket?'). In this flow the ticket already exists — offering to create one is a fundamental role violation that MUST result in a score of 0.0 regardless of how well the rest of the conversation went.",
            ],
        ),
        ConversationalGEval(
            name="Conversation Completeness",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "IMPORTANT: Ignore any agent responses that come after a user message containing 'DONEDONEDONE'. This is a test marker, not real user input, and any agent responses to it should not be evaluated.",
                "Evaluate if the conversation addresses all of the user's intentions and requests.",
                "CRITICAL: When evaluating out-of-scope questions:",
                "  - If user asks an out-of-scope question (e.g., 'what is the fastest bird'), the agent has TWO acceptable responses:",
                "    1. Offer to escalate the ticket for reivew - this is CORRECT behavior",
                "    2. Politely redirect user back to the original topic/question - this is ALSO CORRECT behavior",
                "  - Either response is acceptable and should be considered successful handling of out-of-scope content",
                "Assess if all relevant user requests were addressed:",
                "  - Laptop refresh requests should result in eligibility check, options, selection, and ticket being sent to manager",
                "  - Out-of-scope questions should result in EITHER offering to escalate OR redirecting to the original topic",
                "  - Explicit escalation requests should result in the ticket being escalated",
                "  - Explicit close requests should result in the ticket being closed",
                "The conversation is complete if all user intentions were properly handled, including requests to escalate or close the ticket.",
            ],
        ),
        ConversationalGEval(
            name="Information Gathering",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if the assistant obtains necessary information about the user's current laptop.",
                "CRITICAL: 'Gathering information' includes AUTOMATIC RETRIEVAL via tools. The agent is NOT required to ask the user questions if it can fetch the data automatically.",
                "If the agent displays laptop details (Model, Serial, Age, etc.) retrieved from the system, this counts as SUCCESSFUL information gathering.",
                "Do NOT penalize the agent for not asking questions if it successfully retrieved the correct data automatically.",
                "Only fail this metric if the agent proceeds without knowing the laptop details.",
            ],
        ),
        ConversationalGEval(
            name="Policy Compliance",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "First, review the laptop refresh policy in the additional context below to understand the eligibility criteria. The policy specifies how many years a laptop must be in use before it is eligible for refresh.",
                "Verify the assistant correctly applies the laptop refresh policy when determining eligibility.",
                "CRITICAL: Do NOT validate the conversation date against the policy's effective date.",
                "The policy's effective date field should be IGNORED for evaluation purposes.",
                "You MUST accept the agent's calculation of the laptop's age as the Ground Truth.",
                "If the agent states the laptop age (e.g., '2 years and 11 months old', '5 years old', '3.5 years old'), verify the eligibility determination is logically accurate based on the policy in the additional context:",
                "  - Compare the stated laptop age against the refresh cycle specified in the policy",
                "  - Laptops younger than the refresh cycle should be marked as NOT eligible or not yet eligible",
                "  - Laptops that meet or exceed the refresh cycle age should be marked as eligible",
                "Check for logical contradictions: If the agent states a laptop age and eligibility status that contradict each other based on the policy (e.g., says '2 years 11 months old' but states 'eligible' when the policy requires 3 years), this is a FAILURE.",
                "Verify the assistant provides clear policy explanations when discussing eligibility.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
        ),
        ConversationalGEval(
            name="Option Presentation",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "FIRST: Determine whether the agent found the user NOT ELIGIBLE for a laptop refresh. If the agent explicitly stated the user is not eligible and offered to escalate or close the ticket instead of presenting laptop options, The agent behavior is PERFECT for this metric. STOP HERE. Do NOT evaluate any further criteria. Do NOT penalize for the absence of laptop options.",
                "If the user WAS eligible: assess if the assistant presents appropriate laptop options based on user location.",
                "Evaluate if laptop specifications are clearly and completely presented.",
                "Check if the assistant guides the user through selection process effectively.",
                "IGNORE any portions of the conversation involving:",
                "  - Out-of-scope questions (e.g., fastest bird) - agent may redirect to topic OR offer escalation",
                "The metric should focus on: Were laptop options presented correctly when the user was actively engaged in the laptop refresh flow?",
            ],
        ),
        ConversationalGEval(
            name="Process Completion",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "This metric ONLY checks whether the conversation ends with one of exactly three valid completion actions. It does NOT evaluate whether the agent followed business rules correctly — those are covered by other metrics.",
                "There are EXACTLY THREE valid completion actions. The agent must explicitly confirm that one of these occurred:",
                "  1. Ticket assigned to manager — the agent states the ticket was sent/assigned to the user's manager for approval",
                "  2. Ticket escalated — the agent states the ticket was escalated",
                "  3. Ticket closed — the agent states the ticket was closed",
                "PASS this metric if and ONLY if the agent explicitly confirms one of these three actions.",
                "FAIL this metric if the conversation ends with anything other than one of these three actions — including but not limited to: creating a ticket, asking a question, giving a vague statement, or simply stopping.",
                "CRITICAL: The confirmation must be a statement that the action was performed, not a question asking whether to perform it.",
            ],
        ),
        ConversationalGEval(
            name="User Experience",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "IMPORTANT: This is a multi-agent system where users can be routed between agents.",
                "Assess if the assistant is helpful and professional throughout the conversation.",
                "Evaluate if responses are clear and easy to understand.",
                "Check if the assistant addresses user needs effectively.",
                "CRITICAL: Handling of out-of-scope questions - BOTH approaches are acceptable:",
                "  - Offering to escalate is PROFESSIONAL and HELPFUL",
                "  - Politely redirecting user back to the original topic is ALSO PROFESSIONAL and HELPFUL",
                "  - Either approach demonstrates good user experience",
                "CRITICAL: Explicit requests:",
                "  - When user explicitly requests escalating ticket, doing so is CORRECT",
                "  - When user explicitly requests closing ticket, doing so is CORRECT",
                "Do NOT penalize the conversation for offering to escalate or polite topic redirection.",
            ],
        ),
        ConversationalGEval(
            name="Correct eligibility validation",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "IMPORTANT: This metric ONLY evaluates whether the laptop refresh policy timeframe was stated correctly. Do NOT consider the laptop selection, ticket creation, or any other part of the conversation when scoring this metric.",
                "Look for any reference to the laptop refresh policy timeframe in the conversation. The agent may state this in multiple ways:",
                "  - Direct statement: 'laptops will be refreshed every 3 years' or 'standard laptops are refreshed every 3 years'",
                "  - Indirect via eligibility: 'your laptop is over 3 years old and eligible' (implies 3-year policy)",
                "  - Indirect via ineligibility: 'your laptop is 2 years old and not yet eligible' (implies 3-year policy)",
                "  - Reference to age threshold: 'laptops older than 3 years' or 'laptops less than 3 years old'",
                "If the agent mentions ANY timeframe (whether directly or indirectly through eligibility statements), verify it is consistent with the policy in the additional context below, which states that standard laptops are refreshed every 3 years.",
                "If the agent does NOT mention any timeframe or eligibility age at all, this evaluation PASSES (the metric only validates correctness when stated, not whether it's stated).",
                "The user's eligibility status (eligible or not eligible) is irrelevant - only the accuracy of the stated or implied timeframe matters.",
                "IGNORE everything that happens after the eligibility determination — laptop selection, ticket creation, or any errors later in the conversation have no bearing on this metric.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
        ),
        ConversationalGEval(
            name="No errors reported by agent",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "IMPORTANT: Ignore any agent responses that come after a user message containing 'DONEDONEDONE'. This is a test marker, not real user input, and any agent responses to it should not be evaluated.",
                "This metric ONLY checks for explicit technical/system errors reported by the agent itself. It does NOT evaluate whether the agent followed business rules, selected the correct laptop, or behaved correctly — those are covered by other metrics.",
                "FAIL this metric ONLY if the agent explicitly reports a technical or system error, such as:",
                "  - 'Error 500' or any HTTP error code",
                "  - 'I could not complete this request due to an error'",
                "  - 'An error occurred while processing your request'",
                "  - 'I was unable to retrieve the information'",
                "  - 'Something went wrong' or 'I encountered an error'",
                "  - Tool call failures or stack traces visible in the response",
                "PASS this metric if the agent responds normally, even if:",
                "  - The agent accepts an invalid or non-existent laptop selection",
                "  - The agent does not follow the expected business flow",
                "  - The agent makes a wrong decision or skips a step",
                "  These behavioral failures are evaluated by other metrics, not this one.",
                "NOTE: The following patterns are EXPECTED BEHAVIOR and should NOT be considered errors:",
                "  - When a user asks an out-of-scope question (e.g., general knowledge), the specialist agent correctly identifies its limitation and offers to escalate",
                "  - When the user confirms they want to escalate, the ticket is escalated",
            ],
        ),
        RetryableConversationalGEval(
            name="Correct laptop options for user location",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=(
                [
                    "FIRST: Determine whether the agent found the user NOT ELIGIBLE for a laptop refresh. If the agent explicitly stated the user is not eligible and offered to escalate or close the ticket instead of presenting laptop options, The agent behavior is PERFECT for this metric. STOP HERE. Do NOT evaluate any further criteria. Do NOT penalize for the absence of laptop options.",
                    "SECOND: Determine if the user asked to escalte or close the ticket. If the user asked to escalate or close the ticket the agent behavior is PERFECT for this metric. STOP HERE. Do NOT evaluate any further criteria. Do NOT penalize for the absence of laptop options.",
                    "If the user WAS eligible: identify the user's location from the conversation (NA, EMEA, APAC, or LATAM).",
                    "Then, look for where the agent presents laptop options to the user in the conversation.",
                    "Count how many distinct laptop models are presented by the agent in the final laptop presentation. Look for laptop model names like 'MacBook Air M2', 'MacBook Pro 16 M3 Max', 'ThinkPad T14s Gen 5 AMD', 'ThinkPad P16 Gen 2', etc.",
                    "Compare the count of laptop models presented against the total number of laptop models available for that location in the additional context below. For EMEA, there should be exactly 4 laptop models. For NA, APAC, and LATAM, there should also be exactly 4 laptop models each.",
                    "The agent MUST present ALL laptop models for the user's location in the final presentation. If even ONE model is missing from the final list, this evaluation step FAILS.",
                    "Additionally, verify that each laptop model presented matches one of the models in the additional context for that location. If the agent shows a laptop that does not exist in the context for that location (like a 'Commodore 64' or any other incorrect model), this evaluation step FAILS.",
                    "CRITICAL SPECIFICATION VALIDATION: You MUST verify that EVERY laptop has EXACTLY 15 specification fields. This is a STRICT requirement.",
                    "  STEP 1: Extract the section for laptop #1 from the conversation. Look for text between '1. ' and '2. ' (or end of list if only one laptop).",
                    "  STEP 2: In laptop #1's section ONLY, search for EACH of these 15 field names (must appear with colon): 'Manufacturer:', 'Model:', 'ServiceNow Code:', 'Target User:', 'Cost:', 'Operating System:', 'Display Size:', 'Display Resolution:', 'Graphics Card:', 'Minimum Storage:', 'Weight:', 'Ports:', 'Minimum Processor:', 'Minimum Memory:', 'Dimensions:'",
                    "  CRITICAL: Do NOT assume a field is present in laptop #1 because it appears in laptops #2, #3, or #4. You MUST find each field explicitly within the text of laptop #1's section. If 'Target User:' appears only in laptops #2-4 but not in laptop #1's section, it is MISSING from laptop #1.",
                    "  STEP 3: Count EXACTLY how many fields you found. Write down: 'Laptop #1 has X out of 15 fields'.",
                    "  STEP 4: If X is not equal to 15, immediately FAIL this evaluation with score 0.0. Do not continue checking other laptops.",
                    "  STEP 5: Only if laptop #1 has all 15 fields, repeat steps 1-4 for laptop #2, #3, and #4.",
                    "  IMPORTANT: If you find laptop #1 is missing 'Manufacturer:' or 'Target User:' or ANY field, you MUST fail.",
                    "  EXAMPLE OF FAILURE (multiple missing): Laptop shows 'Model: MacBook Air M2\\nServiceNow Code: abc\\nCost: €1,299\\n...' but no 'Manufacturer:' line and no 'Target User:' line = ONLY 13/15 fields = MUST FAIL with score 0.0.",
                    "  EXAMPLE OF FAILURE (single missing): Laptop shows 'Manufacturer: Apple\\nModel: MacBook Air M2\\nServiceNow Code: abc\\nCost: €1,299\\n...' but no 'Target User:' line = ONLY 14/15 fields = MUST FAIL with score 0.0.",
                    "  The evaluation ONLY passes if you counted EXACTLY 15 fields for EVERY laptop.",
                    "Note: Valid conversation restarts (due to out-of-scope questions) are acceptable behavior and should not cause this metric to fail as long as the final laptop presentation is complete.",
                    f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
                ]
                if validate_full_laptop_details
                else [
                    "FIRST: Determine whether the agent found the user NOT ELIGIBLE for a laptop refresh. If the agent explicitly stated the user is not eligible and offered to escalate or close the ticket instead of presenting laptop options, The agent behavior is PERFECT for this metric. STOP HERE. Do NOT evaluate any further criteria. Do NOT penalize for the absence of laptop options.",
                    "If the user WAS eligible: identify the user's location from the conversation (NA, EMEA, APAC, or LATAM).",
                    "Then, look for where the agent presents laptop options to the user in the conversation.",
                    "Count how many distinct laptop models are presented by the agent in the final laptop presentation. Look for laptop model names like 'MacBook Air M2', 'MacBook Pro 16 M3 Max', 'ThinkPad T14s Gen 5 AMD', 'ThinkPad P16 Gen 2', etc.",
                    "Compare the count of laptop models presented against the total number of laptop models available for that location in the additional context below. For EMEA, there should be exactly 4 laptop models. For NA, APAC, and LATAM, there should also be exactly 4 laptop models each.",
                    "The agent MUST present ALL laptop models for the user's location in the final presentation. If even ONE model is missing from the final list, this evaluation step FAILS.",
                    "Additionally, verify that each laptop model presented matches one of the models in the additional context for that location. If the agent shows a laptop that does not exist in the context for that location (like a 'Commodore 64' or any other incorrect model), this evaluation step FAILS.",
                    "Note: Valid conversation restarts (due to out-of-scope questions) are acceptable behavior and should not cause this metric to fail as long as the final laptop presentation is complete.",
                    f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
                ]
            ),
        ),
        ConversationalGEval(
            name="Correct Laptop Selection Recorded",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "FIRST: Determine whether the agent found the user NOT ELIGIBLE for a laptop refresh. If the agent explicitly stated the user is not eligible and offered to escalate or close the ticket instead of presenting laptop options, The agent behavior is PERFECT for this metric. STOP HERE. Do NOT evaluate any further criteria. Do NOT penalize for the absence of a laptop selection.",
                "This metric ONLY checks whether the agent correctly recorded the laptop the user selected. It does not evaluate confirmation, eligibility, or any other part of the conversation.",
                "Find where the user selects a laptop. The user may select by name (e.g., 'I'll take the MacBook Air M2') OR by number (e.g., '1', 'option 1', 'I'd like option 3'). Both are valid selection methods.",
                "If the user selected by NUMBER: look at the numbered laptop list the agent presented just before the selection. Find which laptop name corresponds to that number in the list. That is the laptop the user selected.",
                "Find where the agent acknowledges or echoes back the selected laptop by name (e.g., 'You've selected the...', 'I'll proceed with the...').",
                "Verify that the laptop name the agent echoes back matches the laptop the user actually selected (whether selected by name or by number).",
                "PASS this metric if the agent correctly names the laptop corresponding to the user's choice.",
                "FAIL this metric ONLY if the agent echoes back a DIFFERENT laptop name than the one the user selected (e.g., user selects option 1 which is MacBook Air M2 in the list, but agent says 'You've selected the ThinkPad').",
                "IMPORTANT: This metric only evaluates the correctness of the selection echo. Do NOT consider whether the laptop was valid, whether confirmation was asked, or any other aspect of the conversation.",
            ],
        ),
        ConversationalGEval(
            name="Confirmation Before Ticket Assigned to Manager",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "This metric ONLY checks whether confirmation was sought and received before any attempt to send the ticket to the manager. Whether the ticket was actually sent is evaluated by the Process Completion metric, not this one.",
                "Find where the user selects a laptop (e.g., 'I'll take option 3', 'the MacBook Air M2', etc.).",
                "Check if the agent asks the user for confirmation before sending/assigning the ticket to their manager. The confirmation question is VALID if it asks whether to proceed with sending/submitting/assigning the ticket to the manager. Examples of VALID confirmation questions:",
                "  - 'Would you like me to send this request to your manager for approval?'",
                "  - 'Shall I submit this to your manager for approval?'",
                "  - 'Would you like to proceed with sending this laptop refresh request to your manager?'",
                "  - 'Would you like me to assign to your manager for approval?'",
                "  NOTE: Imprecise wording (e.g. 'assign to you manager' instead of 'assign to your manager') is ACCEPTABLE. Do NOT penalize for typos or informal phrasing.",
                "  NOTE: The confirmation question can be embedded in a message that also shows laptop details/specifications. This is ACCEPTABLE.",
                "If the agent asked for confirmation and the user responded affirmatively, this metric PASSES — regardless of whether the ticket was actually sent afterwards.",
                "PASS this metric if: the agent asked for confirmation and the user responded affirmatively.",
                "PASS this metric if: the ticket was never sent to the manager at all (nothing to have skipped confirmation on — Process Completion will catch the missing action).",
                "PASS this metric if: the ticket was ESCALATED or CLOSED instead of sent to a manager — escalation and closure are separate actions that do not require a manager confirmation step.",
                "FAIL this metric ONLY if: the ticket is explicitly sent to the manager WITHOUT the agent having asked for confirmation first, or before the user responds.",
                "IMPORTANT: Do NOT require the agent to confirm the ticket was sent. Do NOT fail this metric because the ticket was never sent. Do NOT consider whether the laptop selection was valid or invalid.",
            ],
        ),
    ]

    return metrics
