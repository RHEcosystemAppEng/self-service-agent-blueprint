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
    no_employee_id: bool = False,
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
            - Information Gathering: Evaluates employee ID and laptop info collection
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
            ]
            + (
                []
                if no_employee_id
                else [
                    "Assess if the assistant properly requests employee ID from the user."
                ]
            ),
            **model_kwargs,
        ),
        ConversationalGEval(
            name="Policy Compliance",
            threshold=0.8,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "Assess if the assistant correctly applies laptop refresh policies.",
                "Evaluate if eligibility determination is accurate based on laptop age and warranty.",
                "Check if the assistant provides clear policy explanations.",
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
                "Assess if the assistant guides the user through the complete laptop refresh process.",
                "Evaluate if the assistant confirms user selections appropriately.",
                "Check if the assistant provides clear next steps or completion actions.",
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
                f"Validate that if the agent states the number of years afer which laptops are refreshed, what is says is consistent with the additional context. It is ok if the user is not yet eligible. Do not assess anything other than the number of years stated.\n\nadditional-context-start\n{default_context}\nadditional-context-end",
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
                f"Validate that if the agent provides a list of laptop options in the conversation, the list includes all of the available options in the additional context for the user's location.\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
            **model_kwargs,
        ),
    ]

    # Add employee ID-specific metric only if not excluded
    if not no_employee_id:
        metrics.append(
            ConversationalGEval(
                name="Employeed id requested",
                threshold=1.0,
                evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
                evaluation_steps=[
                    "Validate the assistant asks for the users employee id",
                ],
                **model_kwargs,
            )
        )

    return metrics
