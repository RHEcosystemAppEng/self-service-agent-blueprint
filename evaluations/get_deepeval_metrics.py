#!/usr/bin/env python3
"""
DeepEval metrics configuration for laptop refresh conversation assessment.

This module defines evaluation metrics specifically designed for IT support
conversations related to laptop refresh requests. It provides a comprehensive
suite of conversational metrics for assessing agent performance.
"""

from typing import Any, List, Optional

from deepeval.metrics import ConversationalGEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import TurnParams
from helpers.load_conversation_context import load_default_context


def get_metrics(
    custom_model: Optional[DeepEvalBaseLLM] = None,
) -> List[Any]:
    """
    Create comprehensive evaluation metrics for laptop refresh conversation assessment.

    This function defines a suite of conversational metrics specifically designed
    to evaluate IT support conversations related to laptop refresh requests.
    Includes both standard conversation metrics and custom laptop-specific criteria.

    Args:
        custom_model: Optional custom LLM model instance to use for evaluations.
                     If None, uses the default DeepEval model.

    Returns:
        List[ConversationalGEval]: List of evaluation metrics including:
            - Turn Relevancy: Measures relevance of assistant responses with multi-agent awareness
            - Role Adherence: Evaluates adherence to agent roles with multi-agent routing support
            - Conversation Completeness: Assesses conversation flow completeness with multi-agent routing support
            - Information Gathering: Evaluates laptop info collection
            - Policy Compliance: Checks laptop refresh policy application
            - Option Presentation: Assesses laptop option presentation quality
            - Process Completion: Evaluates complete laptop refresh process
            - User Experience: Measures helpfulness and professionalism
            - Flow Termination: Validates proper conversation ending
            - Ticket Number Validation: Confirms correct ticket format
            - Eligibility Validation: Verifies refresh policy accuracy
            - Error Validation: Checks for system response problems
            - Location-based Options: Validates correct laptop options per location
    """
    default_context = load_default_context()

    metrics = [
        ConversationalGEval(
            name="Turn Relevancy",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if each assistant response is relevant to the user's message and conversation context.",
                "IMPORTANT: This is a multi-agent system where users can be routed between a routing agent and specialist agents.",
                "When evaluating routing agent messages, recognize that the routing agent's role is to:",
                "  - Greet users (including returning users)",
                "  - Ask what they need help with",
                "  - Mention available services (laptop refresh, email updates)",
                "If a routing agent message appears after a completed task (e.g., after ticket creation or after user says DONEDONEDONE), this is RELEVANT because:",
                "  - The user has been returned to the routing agent to start a new request",
                "  - The routing agent is correctly greeting them and offering to help with a new task",
                "  - This is expected multi-agent routing system behavior, not irrelevant repetition",
                "Only mark messages as irrelevant if they:",
                "  - Completely ignore the user's question or request",
                "  - Provide unrelated information",
                "  - Fail to address the user's actual need",
                "Do NOT mark as irrelevant:",
                "  - Routing agent greetings after task completion (this is correct routing behavior)",
                "  - Specialist agent responses that stay within their scope",
                "  - Appropriate redirects to the routing agent for out-of-scope questions",
            ],
        ),
        ConversationalGEval(
            name="Role Adherence",
            threshold=0.5,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "CRITICAL: This is a multi-agent system with a routing agent and specialist agents.",
                "Evaluate if agents adhere to their assigned roles throughout the conversation.",
                "IMPORTANT: Recognize different agent types and their expected behaviors:",
                "  - Routing Agent: Greets users, asks what they need help with, routes to specialists, re-greets after return-to-router",
                "  - Laptop Refresh Specialist: Handles laptop eligibility, options, selection, and ticket creation",
                "Role adherence expectations:",
                "  - Routing agent introducing itself (e.g., 'I'm Rachel, a routing agent') is CORRECT and EXPECTED",
                "  - Routing agent asking 'What can I help you with?' is CORRECT role behavior",
                "  - Routing agent appearing at conversation start or after return-to-router is EXPECTED, not a role violation",
                "  - Laptop refresh specialist checking eligibility before presenting options is CORRECT",
                "  - Laptop refresh specialist presenting location-appropriate options is CORRECT",
                "  - Specialist offering to return to router for out-of-scope questions is CORRECT",
                "Assess if each agent stays within their role responsibilities and provides appropriate responses for their role.",
                "Do NOT penalize routing agent for being a routing agent - this is the correct multi-agent architecture.",
            ],
        ),
        ConversationalGEval(
            name="Conversation Completeness",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "IMPORTANT: This is a multi-agent system where users can be routed between a routing agent and specialist agents.",
                "Evaluate if the conversation addresses all of the user's intentions and requests.",
                "CRITICAL: When evaluating out-of-scope questions:",
                "  - If user asks an out-of-scope question (e.g., 'what is the fastest bird'), the agent has TWO acceptable responses:",
                "    1. Offer to return to router for help with other topics - this is CORRECT behavior",
                "    2. Politely redirect user back to the original topic/question - this is ALSO CORRECT behavior",
                "  - Either response is acceptable and should be considered successful handling of out-of-scope content",
                "CRITICAL: When evaluating explicit return-to-router requests:",
                "  - If user explicitly requests 'return to router' or 'go back', the agent should emit 'task_complete_return_to_router' - this is CORRECT behavior",
                "  - After returning to router, the routing agent will re-greet and ask what they need - this is EXPECTED and CORRECT",
                "  - The conversation continuing after a return-to-router is a SUCCESSFUL flow, not a failure",
                "Assess if all relevant user requests were addressed:",
                "  - Laptop refresh requests should result in eligibility check, options, selection, and ticket creation",
                "  - Out-of-scope questions should result in EITHER offering to return to router OR redirecting to the original topic",
                "  - Explicit return-to-router requests should result in routing back to routing agent",
                "The conversation is complete if all user intentions were properly handled, including routing operations.",
            ],
        ),
        ConversationalGEval(
            name="Information Gathering",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if the assistant gathers necessary information about the user's current laptop.",
                "Check if the assistant follows a logical flow for information collection.",
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
                "IMPORTANT: This is a multi-agent system. Users may be routed between agents, and conversations may include return-to-router operations. Focus evaluation on the laptop refresh portions of the conversation.",
                "Assess if the assistant presents appropriate laptop options based on user location when the user is engaged in the laptop refresh process.",
                "Evaluate if laptop specifications are clearly and completely presented.",
                "Check if the assistant guides the user through selection process effectively.",
                "IGNORE any portions of the conversation involving:",
                "  - Out-of-scope questions (e.g., fastest bird) - agent may redirect to topic OR offer router",
                "  - Return-to-router operations - these are handled by routing logic, not option presentation",
                "The metric should focus on: Were laptop options presented correctly when the user was actively engaged in the laptop refresh flow?",
            ],
        ),
        ConversationalGEval(
            name="Process Completion",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Verify that the assistant guides the user through the laptop refresh process including: eligibility check, presenting laptop options, and facilitating laptop selection.",
                "Check if the assistant acknowledges or references the user's laptop selection in any form (e.g., 'You've selected...', proceeding with that model, or creating a ticket for that laptop). Implicit confirmation through context (like creating a ticket after selection) counts as confirmation.",
                "Verify that the conversation includes a completion action such as creating a ServiceNow ticket, providing a ticket number, or confirming the request has been submitted. Creating a ticket IS a completion action and no additional next steps are required.",
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
                "  - Offering to return to router for help with other topics is PROFESSIONAL and HELPFUL",
                "  - Politely redirecting user back to the original topic is ALSO PROFESSIONAL and HELPFUL",
                "  - Either approach demonstrates good user experience",
                "CRITICAL: Explicit return-to-router requests:",
                "  - When user explicitly requests return to router, doing so is CORRECT",
                "  - The routing agent re-greeting the user after return is EXPECTED, not a flaw",
                "Do NOT penalize the conversation for proper routing operations, agent handoffs, or polite topic redirection.",
            ],
        ),
        ConversationalGEval(
            name="Flow termination",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Find the last meaningful agent message (ignore any agent responses that come after a user message containing 'DONEDONEDONE').",
                "Check if this last meaningful agent message contains a ServiceNow ticket number (starting with REQ, INC, or RITM).",
                "The conversation passes if: (1) The last meaningful agent message contains a ticket number, OR (2) The conversation ends with user saying 'DONEDONEDONE' and the task was completed earlier.",
                "Note: If user says 'DONEDONEDONE', any agent response after that should be ignored for evaluation purposes - it's just the system responding to the marker.",
                "The flow terminates successfully if a ticket was created and delivered, regardless of whether routing agent appears afterward or user sends DONEDONEDONE."
            ],
        ),
        ConversationalGEval(
            name="Ticket number validation",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Check that the first three characters of the ticket number for the laptop request are REQ"
            ],
        ),
        ConversationalGEval(
            name="Correct eligibility validation",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Look for any reference to the laptop refresh policy timeframe in the conversation. The agent may state this in multiple ways:",
                "  - Direct statement: 'laptops will be refreshed every 3 years' or 'standard laptops are refreshed every 3 years'",
                "  - Indirect via eligibility: 'your laptop is over 3 years old and eligible' (implies 3-year policy)",
                "  - Indirect via ineligibility: 'your laptop is 2 years old and not yet eligible' (implies 3-year policy)",
                "  - Reference to age threshold: 'laptops older than 3 years' or 'laptops less than 3 years old'",
                "If the agent mentions ANY timeframe (whether directly or indirectly through eligibility statements), verify it is consistent with the policy in the additional context below, which states that standard laptops are refreshed every 3 years.",
                "If the agent does NOT mention any timeframe or eligibility age at all, this evaluation PASSES (the metric only validates correctness when stated, not whether it's stated).",
                "The user's eligibility status (eligible or not eligible) is irrelevant - only the accuracy of the stated or implied timeframe matters.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
        ),
        ConversationalGEval(
            name="No errors reported by agent",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Validate that there are no problems with system responses",
                "Check for actual system errors or failures such as: tool failures, missing data, inability to retrieve information, incorrect responses, or technical errors",
                "NOTE: The following patterns are EXPECTED BEHAVIOR and should NOT be considered errors or inefficiencies:",
                "  - When a user asks an out-of-scope question (e.g., general knowledge), the specialist agent correctly identifies its limitation and offers to return the user to the routing agent",
                "  - When the user confirms they want to return to the routing agent, the conversation is redirected back to the routing agent",
                "  - The routing agent greets the user again and asks what they need help with (this is the normal routing flow)",
                "  - The user re-states their original request (e.g., 'I would like to refresh my laptop') and is routed back to the specialist agent",
                "  - This return-to-router pattern is intentional system design to handle out-of-scope requests and should receive a PASS score",
                "Only mark as a failure if there are genuine system errors, not when the multi-agent routing system is working as designed",
            ],
        ),
        ConversationalGEval(
            name="Correct laptop options for user location",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "First, identify the user's location from the conversation (NA, EMEA, APAC, or LATAM).",
                "Then, look for where the agent presents laptop options to the user in the conversation.",
                "IMPORTANT: If the conversation includes a return-to-router pattern (user asks out-of-scope question, returns to routing agent, then restarts laptop refresh), use the LAST/FINAL presentation of laptop options for evaluation, not the initial one.",
                "Count how many distinct laptop models are presented by the agent in the final laptop presentation. Look for laptop model names like 'MacBook Air M2', 'MacBook Pro 16 M3 Max', 'ThinkPad T14s Gen 5 AMD', 'ThinkPad P16 Gen 2', etc.",
                "Compare the count of laptop models presented against the total number of laptop models available for that location in the additional context below. For EMEA, there should be exactly 4 laptop models. For NA, APAC, and LATAM, there should also be exactly 4 laptop models each.",
                "The agent MUST present ALL laptop models for the user's location in the final presentation. If even ONE model is missing from the final list, this evaluation step FAILS.",
                "Additionally, verify that each laptop model presented matches one of the models in the additional context for that location. If the agent shows a laptop that does not exist in the context for that location (like a 'Commodore 64' or any other incorrect model), this evaluation step FAILS.",
                "Note: Valid conversation restarts (due to out-of-scope questions) are acceptable behavior and should not cause this metric to fail as long as the final laptop presentation is complete.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
        ),
        ConversationalGEval(
            name="Confirmation Before Ticket Creation",
            threshold=1.0,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Identify where in the conversation the user selects a laptop (e.g., selecting option '3', saying 'I'll go with the MacBook', etc.).",
                "Identify where in the conversation a ServiceNow ticket is created (look for ticket numbers like 'REQ' followed by numbers, or statements like 'A ServiceNow ticket has been created').",
                "Between the laptop selection and ticket creation, verify that:",
                "  a) The agent explicitly asks the user for confirmation to proceed with ticket creation (e.g., 'Would you like to proceed with creating a ServiceNow ticket?', 'Shall I create the ticket?', 'Would you like me to submit this request?', etc.)",
                "  b) The user has an opportunity to respond with their confirmation (e.g., 'proceed', 'yes', 'go ahead', etc.)",
                "  c) The ticket creation happens AFTER the user confirms, not before",
                "If the ticket is created immediately after laptop selection without the agent first asking for confirmation and waiting for user response, this evaluation FAILS.",
                "Note: The confirmation question must come from the agent BEFORE the ticket is created. If the agent creates the ticket and then asks 'Is there anything else I can help you with?', this does NOT count as confirmation - the ticket was already created.",
            ],
        ),
        ConversationalGEval(
            name="Return to Router After Task Completion",
            threshold=0.5,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Only fail if: (1) agent asks 'Is there anything else I can help you with?' AND (2) user says 'no' AND (3) routing agent does NOT appear.",
                "If agent does not ask the question, pass.",
                "If conversation ends after the question with no user response, pass.",
                "If user responds but does not say 'no' (says 'yes', asks another question, etc.), pass.",
                "If user says 'no' and routing agent appears (text contains 'routing agent' or mentions both 'laptop refresh' and 'email'), pass.",
                "Fail only if all three conditions are met: agent asks, user says no, no routing agent appears.",
            ],
        ),
    ]

    return metrics
