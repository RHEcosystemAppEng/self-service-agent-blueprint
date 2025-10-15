#!/usr/bin/env python3
"""
DeepEval metrics configuration for laptop refresh conversation assessment.

This module defines evaluation metrics specifically designed for IT support
conversations related to laptop refresh requests. It provides a comprehensive
suite of conversational metrics for assessing agent performance.
"""

from typing import List, Optional

from deepeval.metrics import (
    ConversationalGEval,
    ConversationCompletenessMetric,
    RoleAdherenceMetric,
    TurnRelevancyMetric,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import TurnParams
from helpers.load_conversation_context import load_default_context


def get_metrics(
    custom_model: Optional[DeepEvalBaseLLM] = None,
) -> List[ConversationalGEval]:
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
            - Turn Relevancy: Measures relevance of assistant responses
            - Role Adherence: Evaluates adherence to IT support agent role
            - Conversation Completeness: Assesses conversation flow completeness
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
    # Prepare model configuration for all metrics
    model_kwargs = {"model": custom_model}

    default_context = load_default_context()

    metrics = [
        TurnRelevancyMetric(
            threshold=0.8,
            **model_kwargs,
        ),
        RoleAdherenceMetric(
            threshold=0.5,
            **model_kwargs,
        ),
        ConversationCompletenessMetric(
            threshold=0.8,
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Information Gathering",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Evaluate if the assistant gathers necessary information about the user's current laptop.",
                "Check if the assistant follows a logical flow for information collection.",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Policy Compliance",
            threshold=0.8,
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
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Option Presentation",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Assess if the assistant presents appropriate laptop options based on user location.",
                "Evaluate if laptop specifications are clearly and completely presented.",
                "Check if the assistant guides the user through selection process effectively.",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Process Completion",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Verify that the assistant guides the user through the laptop refresh process including: eligibility check, presenting laptop options, and facilitating laptop selection.",
                "Check if the assistant acknowledges or references the user's laptop selection in any form (e.g., 'You've selected...', proceeding with that model, or creating a ticket for that laptop). Implicit confirmation through context (like creating a ticket after selection) counts as confirmation.",
                "Verify that the conversation includes a completion action such as creating a ServiceNow ticket, providing a ticket number, or confirming the request has been submitted. Creating a ticket IS a completion action and no additional next steps are required.",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="User Experience",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Assess if the assistant is helpful and professional throughout the conversation.",
                "Evaluate if responses are clear and easy to understand.",
                "Check if the assistant addresses user needs effectively.",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Flow termination",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Check if the conversation ends with DONEDONEDONE or the agent returning a service now ticket number to the user. If the ends in any other way the conversation failed"
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Ticket number validation",
            threshold=1.0,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Check that the first three characters of the ticket number for the laptop request are REQ"
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Correct eligibility validation",
            threshold=1.0,
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
            **model_kwargs,
        ),
        ConversationalGEval(
            name="No errors reported by agent",
            threshold=1.0,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Validate that there are no problems with system responses",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Correct laptop options for user location",
            threshold=1.0,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "First, identify the user's location from the conversation (NA, EMEA, APAC, or LATAM).",
                "Then, look for where the agent presents laptop options to the user in the conversation.",
                "Count how many distinct laptop models are presented by the agent. Look for laptop model names like 'MacBook Air M2', 'MacBook Pro 16 M3 Max', 'ThinkPad T14s Gen 5 AMD', 'ThinkPad P16 Gen 2', etc.",
                "Compare the count of laptop models presented against the total number of laptop models available for that location in the additional context below. For EMEA, there should be exactly 4 laptop models. For NA, APAC, and LATAM, there should also be exactly 4 laptop models each.",
                "The agent MUST present ALL laptop models for the user's location. If even ONE model is missing from the list, this evaluation step FAILS.",
                "Additionally, verify that each laptop model presented matches one of the models in the additional context for that location. If the agent shows a laptop that does not exist in the context for that location (like a 'Commodore 64' or any other incorrect model), this evaluation step FAILS.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Confirmation Before Ticket Creation",
            threshold=1.0,
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
            **model_kwargs,
        ),
    ]

    return metrics
