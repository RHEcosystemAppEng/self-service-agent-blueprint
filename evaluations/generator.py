#!/usr/bin/env python3
"""
Conversation Generator for Agent Testing

This script generates conversational test cases by simulating user interactions
with the actual self-service agent. It uses:
- Custom LLM endpoint to simulate realistic user behavior
- OpenShift client to test the actual deployed agent

Each conversation is generated sequentially to ensure proper resource management
and clearer progress tracking. The generated conversations are automatically
saved to results/conversation_results/ with unique timestamped filenames in
the same format as success-flow-1.json.

Required Environment Variables:
- LLM_API_TOKEN: API key/token for the LLM endpoint (for user simulation)
- LLM_URL: Base URL for the LLM API endpoint (for user simulation)
- LLM_ID: (Optional) Model ID to use for user simulation

Required Infrastructure:
- Self-service agent deployed in OpenShift (accessible via 'oc exec')

Usage:
    export LLM_API_TOKEN="your-api-key"
    export LLM_URL="https://your-llm-endpoint.com/v1"
    export LLM_ID="your-model-name"
    python generator.py 3 --max-turns 15
"""

import argparse
import datetime
import json
import logging
import os
import random
from pathlib import Path
from typing import List

from deepeval.dataset import ConversationalGolden
from deepeval.simulator import ConversationSimulator
from deepeval.test_case import ConversationalTestCase, Turn
from helpers.custom_llm import CustomLLM, get_api_configuration
from helpers.openshift_chat_client import OpenShiftChatClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the OpenShift client (for agent under test) - will be updated with test_script in main
client = None

# Track app tokens separately from evaluation tokens
total_app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}

random.seed()


def _load_random_authoritative_user_id() -> str:
    """Load and return a random user ID from the conversations_config/authoritative_user_ids file."""
    user_ids_file = Path("conversations_config/authoritative_user_ids")

    if not user_ids_file.exists():
        raise FileNotFoundError(f"Required file not found: {user_ids_file}")

    with open(user_ids_file, "r") as f:
        user_ids = [line.strip() for line in f if line.strip()]

    if not user_ids:
        raise ValueError(f"No user IDs found in {user_ids_file}")

    return random.choice(user_ids)


def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the conversation generator."""
    parser = argparse.ArgumentParser(
        description="Generate conversational test cases for agent testing"
    )
    parser.add_argument(
        "num_conversations",
        type=int,
        nargs="?",
        default=1,
        help="Number of conversations to generate (default: 1)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Maximum number of turns per conversation (default: 20)",
    )
    parser.add_argument(
        "--test-script",
        type=str,
        default="chat.py",
        help="Name of the test script to execute (default: chat.py)",
    )
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Send 'reset' message at the start of each conversation",
    )
    return parser.parse_args()


def _create_conversation_golden(conversation_number: int) -> ConversationalGolden:
    """Create a single ConversationalGolden object for simulation."""
    # Use conversation number to ensure reproducible but varied employee IDs
    employee_id = random.randint(1001, 1010)

    conversation_golden = ConversationalGolden(
        scenario="An Employee wants to refresh their laptop, they do not share their employee id until asked for it. The agent shows them a list they can choose from, they select the appropriate laptop and a service now ticket number is returned.",
        expected_outcome="They get a Service now ticket number for their refresh request",
        user_description=f"user with employee id {employee_id} who tries to answer the asssitants last question",
    )

    return conversation_golden


# Define chatbot callback to test the actual agent
async def _model_callback(input: str, turns: List[Turn], thread_id: str) -> Turn:
    try:
        logger.info(
            f"model_callback called with input: '{input}', turns count: {len(turns)}, thread_id: {thread_id}"
        )

        logger.info(f"Sending to agent: {input}")
        response = client.send_message(input)

        # Check if we got a valid response
        if response is None:
            logger.error("Agent returned None response")
            response = "I apologize, but I didn't receive a response from the system."
        elif isinstance(response, str) and not response.strip():
            logger.error("Agent returned empty response")
            response = "I apologize, but I received an empty response from the system."

        logger.info(f"Agent response: '{response}'")
        return Turn(role="assistant", content=response)

    except Exception as e:
        logger.error(f"Error getting response from agent: {e}", exc_info=True)
        return Turn(
            role="assistant",
            content="I apologize, but I'm experiencing technical difficulties. Please try again later.",
        )


def _convert_test_case_to_conversation_format(
    test_case: ConversationalTestCase, authoritative_user_id: str
) -> dict:
    """
    Convert a ConversationalTestCase to the conversation results format

    Args:
        test_case: ConversationalTestCase from deepeval
        authoritative_user_id: The authoritative user ID for this conversation

    Returns:
        Dictionary with metadata and conversation turns in the new format
    """
    conversation_turns = []

    # Extract turns from the test case
    if hasattr(test_case, "turns") and test_case.turns:
        for turn in test_case.turns:
            conversation_turns.append({"role": turn.role, "content": turn.content})

    return {
        "metadata": {
            "authoritative_user_id": authoritative_user_id,
            "description": "Generated conversation from deepeval simulation",
        },
        "conversation": conversation_turns,
    }


def _save_conversation_to_file(
    conversation: dict, base_filename: str = "generated_conversation"
) -> str:
    """
    Save conversation to a uniquely named file in results/conversation_results

    Args:
        conversation: Dictionary with metadata and conversation turns
        base_filename: Base name for the file (will have timestamp added)

    Returns:
        The path to the saved file
    """
    # Create results directory if it doesn't exist
    results_dir = "results/conversation_results"
    os.makedirs(results_dir, exist_ok=True)

    # Generate unique filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_filename}_{timestamp}.json"
    filepath = os.path.join(results_dir, filename)

    # Save conversation to file
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(conversation, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved conversation to: {filepath}")
    return filepath


# Run Simulation
if __name__ == "__main__":
    # Parse command line arguments
    args = _parse_arguments()

    # OpenShift client will be created per conversation with different user IDs
    client = None

    # Get API configuration from environment variables
    api_key, api_endpoint, model_name = get_api_configuration()

    if not api_key:
        logger.error("No API key found. Set LLM_API_TOKEN environment variable.")
        exit(1)

    if not api_endpoint:
        logger.error("No API endpoint found. Set LLM_URL environment variable.")
        exit(1)

    # Initialize the custom LLM (for user simulation)
    custom_llm = CustomLLM(
        api_key=api_key, base_url=api_endpoint, model_name=model_name
    )

    logger.info(
        f"Starting conversation simulation with model: {custom_llm.get_model_name()}"
    )
    logger.info(f"Generating {args.num_conversations} conversation(s) sequentially")
    logger.info(f"Maximum user simulations per conversation: {args.max_turns}")

    try:

        # Use custom LLM for user simulation, OpenShift client for agent responses
        logger.info("Creating ConversationSimulator...")
        simulator = ConversationSimulator(
            model_callback=_model_callback,  # Uses OpenShift client to test actual agent
            simulator_model=custom_llm,  # Uses custom LLM to simulate user behavior
        )

        # Generate conversations sequentially
        saved_files = []
        all_test_cases = []

        for i in range(args.num_conversations):
            conversation_number = i + 1
            logger.info(
                f"Generating conversation {conversation_number} of {args.num_conversations}..."
            )

            try:
                # Get a new authoritative user ID for this conversation
                conversation_user_id = _load_random_authoritative_user_id()
                logger.info(
                    f"Conversation {conversation_number} using authoritative user ID: {conversation_user_id}"
                )

                # Create a new OpenShift client for this conversation with unique user ID
                client = OpenShiftChatClient(
                    conversation_user_id,
                    test_script=args.test_script,
                    reset_conversation=args.reset_conversation,
                )

                # Create a single conversation golden for this iteration
                conversation_golden = _create_conversation_golden(conversation_number)

                # Start the OpenShift client session for agent interaction
                try:
                    client.start_session()
                    client.get_agent_initialization()
                except Exception as e:
                    logger.error(
                        f"Failed to start OpenShift client session: {e}", exc_info=True
                    )
                    raise

                # Simulate this single conversation
                logger.info(
                    f"Running simulation for conversation {conversation_number}..."
                )
                conversational_test_cases = simulator.simulate(
                    conversational_goldens=[conversation_golden],
                    max_user_simulations=args.max_turns,
                )
                logger.info(
                    f"Conversation {conversation_number} simulation completed successfully"
                )

                # Request token summary before closing
                try:
                    if client.session_active:
                        logger.info("Requesting token summary from agent...")
                        token_response = client.send_message("**tokens**")
                        logger.info(f"Token request response: {token_response}")
                except Exception as e:
                    logger.warning(f"Failed to request tokens: {e}")

                client.close_session()

                # Collect app tokens from this conversation
                app_tokens = client.get_app_tokens()
                total_app_tokens["input"] += app_tokens["input"]
                total_app_tokens["output"] += app_tokens["output"]
                total_app_tokens["total"] += app_tokens["total"]
                total_app_tokens["calls"] += app_tokens["calls"]

                logger.info(
                    f"App tokens from conversation {conversation_number}: {app_tokens}"
                )

                # Process the generated test case(s) for this conversation
                for j, test_case in enumerate(conversational_test_cases):
                    test_case_number = len(all_test_cases) + 1
                    all_test_cases.append(test_case)

                    print(
                        f"\n=== Test Case {test_case_number} (Conversation {conversation_number}) ==="
                    )
                    print(test_case)

                    # Convert to conversation format and save
                    conversation = _convert_test_case_to_conversation_format(
                        test_case, conversation_user_id
                    )
                    if conversation.get(
                        "conversation"
                    ):  # Only save if we have actual conversation turns
                        base_filename = f"generated_flow_{test_case_number}"
                        saved_file = _save_conversation_to_file(
                            conversation, base_filename
                        )
                        saved_files.append(saved_file)
                        logger.info(
                            f"Test case {test_case_number} saved to: {saved_file}"
                        )
                    else:
                        logger.warning(
                            f"Test case {test_case_number} had no conversation turns to save"
                        )

            except Exception as e:
                logger.error(
                    f"Error during conversation {conversation_number} simulation: {e}",
                    exc_info=True,
                )
                # Continue with the next conversation instead of failing completely
                continue

        logger.info(
            f"Sequential generation completed. Generated {len(all_test_cases)} total test cases"
        )

        if saved_files:
            print("\n=== Saved Conversations ===")
            for file_path in saved_files:
                print(f"- {file_path}")
        else:
            logger.warning("No conversation files were saved")

    except Exception as e:
        logger.error(f"Error during simulation: {e}", exc_info=True)
    finally:
        # Client sessions are closed per conversation, no global cleanup needed
        logger.info("All conversations completed")

        # Final token summary even if there were errors
        from helpers.token_counter import print_token_summary

        print_token_summary(app_tokens=total_app_tokens, save_file_prefix="generator")
