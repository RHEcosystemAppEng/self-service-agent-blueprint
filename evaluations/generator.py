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
from typing import List

from deepeval.dataset import ConversationalGolden
from deepeval.simulator import ConversationSimulator
from deepeval.test_case import ConversationalTestCase, Turn
from helpers.custom_llm import CustomLLM, get_api_configuration
from helpers.openshift_chat_client import OpenShiftChatClient
from helpers.token_counter import get_token_stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the OpenShift client (for agent under test) - will be updated with test_script in main
client = None

# Track app tokens separately from evaluation tokens
total_app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}

random.seed()


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
    test_case: ConversationalTestCase,
) -> List[dict]:
    """
    Convert a ConversationalTestCase to the conversation results format

    Args:
        test_case: ConversationalTestCase from deepeval

    Returns:
        List of conversation turns in the format used by success-flow-1.json
    """
    conversation = []

    # Extract turns from the test case
    if hasattr(test_case, "turns") and test_case.turns:
        for turn in test_case.turns:
            conversation.append({"role": turn.role, "content": turn.content})

    return conversation


def _save_conversation_to_file(
    conversation: List[dict], base_filename: str = "generated_conversation"
) -> str:
    """
    Save conversation to a uniquely named file in results/conversation_results

    Args:
        conversation: List of conversation turns
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

    # Initialize the OpenShift client with the test script parameter
    client = OpenShiftChatClient(test_script=args.test_script)

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
                    conversation = _convert_test_case_to_conversation_format(test_case)
                    if conversation:  # Only save if we have actual conversation turns
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

        # Print token usage summary with separate app and evaluation tokens
        print("\n=== Token Usage Summary ===")

        # Get evaluation token stats
        eval_stats = get_token_stats()

        # Display app tokens (from chat-lg-state.py via oc exec)
        print("\n📱 App Tokens (from chat agent):")
        print(f"  Input tokens: {total_app_tokens['input']:,}")
        print(f"  Output tokens: {total_app_tokens['output']:,}")
        print(f"  Total tokens: {total_app_tokens['total']:,}")
        print(f"  API calls: {total_app_tokens['calls']:,}")

        # Display evaluation tokens (from evaluation LLM calls)
        print("\n🔬 Evaluation Tokens (from evaluation LLM calls):")
        print(f"  Input tokens: {eval_stats.total_input_tokens:,}")
        print(f"  Output tokens: {eval_stats.total_output_tokens:,}")
        print(f"  Total tokens: {eval_stats.total_tokens:,}")
        print(f"  API calls: {eval_stats.call_count:,}")
        if eval_stats.call_count > 0:
            print(f"  Max single request input: {eval_stats.max_input_tokens:,}")
            print(f"  Max single request output: {eval_stats.max_output_tokens:,}")
            print(f"  Max single request total: {eval_stats.max_total_tokens:,}")

        # Display combined totals
        combined_input = total_app_tokens["input"] + eval_stats.total_input_tokens
        combined_output = total_app_tokens["output"] + eval_stats.total_output_tokens
        combined_total = total_app_tokens["total"] + eval_stats.total_tokens
        combined_calls = total_app_tokens["calls"] + eval_stats.call_count

        # Calculate combined maximums (we don't have max values for app tokens yet)
        combined_max_input = (
            eval_stats.max_input_tokens
        )  # Only have eval maximums for now
        combined_max_output = eval_stats.max_output_tokens
        combined_max_total = eval_stats.max_total_tokens

        print("\n📊 Combined Totals:")
        print(f"  Input tokens: {combined_input:,}")
        print(f"  Output tokens: {combined_output:,}")
        print(f"  Total tokens: {combined_total:,}")
        print(f"  API calls: {combined_calls:,}")
        if combined_calls > 0:
            print(f"  Max single request input: {combined_max_input:,}")
            print(f"  Max single request output: {combined_max_output:,}")
            print(f"  Max single request total: {combined_max_total:,}")

        # Save token stats to file
        if eval_stats.call_count > 0 or total_app_tokens["calls"] > 0:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            token_dir = "results/token_usage"
            token_file = os.path.join(token_dir, f"generator_{timestamp}.json")

            # Create comprehensive token data including app and evaluation tokens
            comprehensive_stats = {
                "summary": {
                    "total_input_tokens": combined_input,
                    "total_output_tokens": combined_output,
                    "total_tokens": combined_total,
                    "call_count": combined_calls,
                    "max_input_tokens": combined_max_input,
                    "max_output_tokens": combined_max_output,
                    "max_total_tokens": combined_max_total,
                },
                "app_tokens": {
                    **total_app_tokens,
                    "max_input": 0,  # App tokens don't have max tracking yet
                    "max_output": 0,
                    "max_total": 0,
                },
                "evaluation_tokens": {
                    "total_input_tokens": eval_stats.total_input_tokens,
                    "total_output_tokens": eval_stats.total_output_tokens,
                    "total_tokens": eval_stats.total_tokens,
                    "call_count": eval_stats.call_count,
                    "max_input_tokens": eval_stats.max_input_tokens,
                    "max_output_tokens": eval_stats.max_output_tokens,
                    "max_total_tokens": eval_stats.max_total_tokens,
                },
                "detailed_calls": getattr(eval_stats, "detailed_calls", []),
            }

            os.makedirs(token_dir, exist_ok=True)
            with open(token_file, "w") as f:
                json.dump(comprehensive_stats, f, indent=2)
            print(f"Token usage saved to: {token_file}")

    except Exception as e:
        logger.error(f"Error during simulation: {e}", exc_info=True)
    finally:
        # Always close the session
        logger.info("Closing OpenShift client session...")
        try:
            client.close_session()
            logger.info("OpenShift client session closed successfully")
        except Exception as e:
            logger.error(f"Error closing session: {e}", exc_info=True)

        # Final token summary even if there were errors
        print("\n=== Final Token Usage Summary ===")

        # Get evaluation token stats
        eval_stats = get_token_stats()

        # Display app tokens (from chat-lg-state.py via oc exec)
        print("\n📱 App Tokens (from chat agent):")
        print(f"  Input tokens: {total_app_tokens['input']:,}")
        print(f"  Output tokens: {total_app_tokens['output']:,}")
        print(f"  Total tokens: {total_app_tokens['total']:,}")
        print(f"  API calls: {total_app_tokens['calls']:,}")

        # Display evaluation tokens (from evaluation LLM calls)
        print("\n🔬 Evaluation Tokens (from evaluation LLM calls):")
        print(f"  Input tokens: {eval_stats.total_input_tokens:,}")
        print(f"  Output tokens: {eval_stats.total_output_tokens:,}")
        print(f"  Total tokens: {eval_stats.total_tokens:,}")
        print(f"  API calls: {eval_stats.call_count:,}")
        if eval_stats.call_count > 0:
            print(f"  Max single request input: {eval_stats.max_input_tokens:,}")
            print(f"  Max single request output: {eval_stats.max_output_tokens:,}")
            print(f"  Max single request total: {eval_stats.max_total_tokens:,}")

        # Display combined totals
        combined_input = total_app_tokens["input"] + eval_stats.total_input_tokens
        combined_output = total_app_tokens["output"] + eval_stats.total_output_tokens
        combined_total = total_app_tokens["total"] + eval_stats.total_tokens
        combined_calls = total_app_tokens["calls"] + eval_stats.call_count

        # Calculate combined maximums (we don't have max values for app tokens yet)
        combined_max_input = (
            eval_stats.max_input_tokens
        )  # Only have eval maximums for now
        combined_max_output = eval_stats.max_output_tokens
        combined_max_total = eval_stats.max_total_tokens

        print("\n📊 Combined Totals:")
        print(f"  Input tokens: {combined_input:,}")
        print(f"  Output tokens: {combined_output:,}")
        print(f"  Total tokens: {combined_total:,}")
        print(f"  API calls: {combined_calls:,}")
        if combined_calls > 0:
            print(f"  Max single request input: {combined_max_input:,}")
            print(f"  Max single request output: {combined_max_output:,}")
            print(f"  Max single request total: {combined_max_total:,}")
