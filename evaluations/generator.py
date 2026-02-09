#!/usr/bin/env python3
"""
Conversation Generator for Agent Testing

This script generates conversational test cases by simulating user interactions
with the actual self-service agent. It uses:
- Custom LLM endpoint to simulate realistic user behavior
- OpenShift client to test the actual deployed agent

The generator supports two execution modes:
1. Sequential (default): Conversations are generated one at a time
2. Concurrent: Multiple workers generate conversations in parallel

In concurrent mode (--concurrency N):
- N workers run in parallel, each with its own OpenShift client
- Each worker uses a different subset of users (no overlap)
- Each worker generates the requested number of conversations
- Total conversations = N * num_conversations
- Concurrency cannot exceed the number of available users

The generated conversations are automatically saved to
results/conversation_results/ with unique timestamped filenames.

Required Environment Variables:
- LLM_API_TOKEN: API key/token for the LLM endpoint (for user simulation)
- LLM_URL: Base URL for the LLM API endpoint (for user simulation)
- LLM_ID: (Optional) Model ID to use for user simulation

Required Infrastructure:
- Self-service agent deployed in OpenShift (accessible via 'oc exec')

Usage:
    # Sequential mode (default)
    export LLM_API_TOKEN="your-api-key"
    export LLM_URL="https://your-llm-endpoint.com/v1"
    export LLM_ID="your-model-name"
    python generator.py 3 --max-turns 15

    # Concurrent mode (4 workers, 10 conversations each = 40 total)
    python generator.py 10 --max-turns 15 --concurrency 4
"""

import argparse
import datetime
import json
import logging
import os
import random
from multiprocessing import Pool
from pathlib import Path
from typing import Any, List, Optional

from deepeval.dataset import ConversationalGolden
from deepeval.simulator import ConversationSimulator
from deepeval.test_case import ConversationalTestCase, Turn
from helpers.custom_llm import CustomLLM, get_api_configuration
from helpers.openshift_chat_client import OpenShiftChatClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

random.seed()


def _load_all_authoritative_user_ids() -> List[str]:
    """Load all user IDs from the conversations_config/authoritative_user_ids file."""
    user_ids_file = Path("conversations_config/authoritative_user_ids")

    if not user_ids_file.exists():
        raise FileNotFoundError(f"Required file not found: {user_ids_file}")

    with open(user_ids_file, "r") as f:
        user_ids = [line.strip() for line in f if line.strip()]

    if not user_ids:
        raise ValueError(f"No user IDs found in {user_ids_file}")

    return user_ids


def _load_random_authoritative_user_id(user_ids: Optional[List[str]] = None) -> str:
    """Load and return a random user ID from the given list or from file if not provided."""
    if user_ids is None:
        user_ids = _load_all_authoritative_user_ids()

    if not user_ids:
        raise ValueError("No user IDs available")

    return random.choice(user_ids)


def _partition_user_ids(user_ids: List[str], num_partitions: int) -> List[List[str]]:
    """
    Partition user IDs into num_partitions groups with no overlap.
    Each partition gets an equal or near-equal number of users.

    Args:
        user_ids: List of all user IDs
        num_partitions: Number of partitions to create

    Returns:
        List of user ID lists, one per partition
    """
    if num_partitions <= 0:
        raise ValueError("num_partitions must be positive")

    if num_partitions > len(user_ids):
        raise ValueError(
            f"Cannot create {num_partitions} partitions from {len(user_ids)} users. "
            f"Concurrency cannot exceed the number of available users."
        )

    # Calculate partition sizes
    partition_size = len(user_ids) // num_partitions
    remainder = len(user_ids) % num_partitions

    partitions = []
    start_idx = 0

    for i in range(num_partitions):
        # Give extra user to first 'remainder' partitions
        size = partition_size + (1 if i < remainder else 0)
        end_idx = start_idx + size
        partitions.append(user_ids[start_idx:end_idx])
        start_idx = end_idx

    return partitions


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
        help="Number of conversations to generate per worker (default: 1)",
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
        default="chat-responses-request-mgr.py",
        help="Name of the test script to execute (default: chat-responses-request-mgr.py)",
    )
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Send 'reset' message at the start of each conversation",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1). Each worker generates num_conversations conversations. "
        "Total conversations = concurrency * num_conversations. "
        "Cannot exceed the number of available users.",
    )
    parser.add_argument(
        "--message-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for individual message send/response operations (default: 60). "
        "Increase for slower agents or high concurrency scenarios.",
    )
    parser.add_argument(
        "--use-structured-output",
        action="store_true",
        default=False,
        help="Enable structured output mode using Pydantic schema validation with retries. "
        "Recommended for models like Gemini that benefit from explicit schema validation.",
    )
    return parser.parse_args()


def _create_conversation_golden(
    conversation_number: int, use_structured_output: bool = False
) -> ConversationalGolden:
    """Create a single ConversationalGolden object for simulation based on the use_structured_output flag."""

    if use_structured_output:
        # for models with structured output like Gemini
        scenario = "An Employee wants to refresh their laptop. The user initiates the conversation by asking to refresh their laptop. Then, if the agent provides a list of options, the user selects the appropriate laptop."
        user_description = "An employee interacting with an IT self-service agent."
    else:
        # for models without structured output like Llama
        scenario = "An Employee wants to refresh their laptop. The agent shows them a list they can choose from, they select the appropriate laptop and a service now ticket number is returned."
        user_description = "user who tries to answer the asssitants last question"

    conversation_golden = ConversationalGolden(
        scenario=scenario,
        expected_outcome="They get a Service now ticket number for their refresh request",
        user_description=user_description,
    )

    return conversation_golden


def _run_worker(
    worker_id: int,
    user_ids: List[str],
    num_conversations: int,
    max_turns: int,
    test_script: str,
    reset_conversation: bool,
    message_timeout: int = 60,
    use_structured_output: bool = False,
) -> dict[str, Any]:
    """
    Worker function to generate conversations in parallel.

    Args:
        worker_id: ID of this worker (0-indexed)
        user_ids: List of user IDs assigned to this worker
        num_conversations: Number of conversations to generate
        max_turns: Maximum turns per conversation
        test_script: Test script to use
        reset_conversation: Whether to reset conversation at start
        message_timeout: Timeout for individual message send/response operations
        use_structured_output: Enable structured output with Pydantic schema validation

    Returns:
        Dictionary with saved_files, token_counts, and test_case_count
    """
    # Configure logging for this worker
    worker_logger = logging.getLogger(f"worker-{worker_id}")
    worker_logger.info(
        f"Worker {worker_id} starting with {len(user_ids)} user IDs: {user_ids}"
    )
    worker_logger.info(
        f"Worker {worker_id} will generate {num_conversations} conversation(s)"
    )

    # Get API configuration
    api_key, api_endpoint, model_name = get_api_configuration()

    # Validate required configuration
    if not api_key:
        raise ValueError("API key is required. Set LLM_API_TOKEN environment variable.")
    if not api_endpoint:
        raise ValueError("API endpoint is required. Set LLM_URL environment variable.")

    # Initialize the custom LLM for this worker
    custom_llm = CustomLLM(
        api_key=api_key,
        base_url=api_endpoint,
        model_name=model_name,
        use_structured_output=use_structured_output,
    )

    # Create a client variable for this worker
    worker_client: Optional[OpenShiftChatClient] = None

    # Define model callback for this worker
    async def worker_model_callback(
        input: str, turns: List[Turn], thread_id: str
    ) -> Turn:
        try:
            worker_logger.info(
                f"[Worker {worker_id}] model_callback called with input: '{input[:100]}...'"
            )

            if worker_client is None:
                worker_logger.error(
                    f"[Worker {worker_id}] OpenShift client not initialized"
                )
                return Turn(
                    role="assistant",
                    content="I apologize, but the system is not properly initialized.",
                )

            response = worker_client.send_message(input)

            # Enhanced validation and logging for empty responses
            if isinstance(response, str) and not response.strip():
                worker_logger.error(
                    f"[Worker {worker_id}] Agent returned empty response - "
                    f"input_length={len(input)}, turn_count={len(turns)}, thread_id={thread_id}, "
                    f"session_active={worker_client.session_active}"
                )
                response = (
                    "I apologize, but I received an empty response from the system."
                )
            elif not isinstance(response, str):
                worker_logger.error(
                    f"[Worker {worker_id}] Agent returned non-string response: type={type(response)}"
                )
                response = (
                    "I apologize, but I received an invalid response from the system."
                )
            else:
                worker_logger.info(
                    f"[Worker {worker_id}] Agent response received: length={len(response)}"
                )

            worker_logger.debug(
                f"[Worker {worker_id}] Response preview: '{response[:200]}...'"
            )
            return Turn(role="assistant", content=response)

        except Exception as e:
            worker_logger.error(
                f"[Worker {worker_id}] Error getting response: {e}", exc_info=True
            )
            return Turn(
                role="assistant",
                content="I apologize, but I'm experiencing technical difficulties.",
            )

    # Create simulator for this worker
    simulator = ConversationSimulator(
        model_callback=worker_model_callback,  # type: ignore[arg-type]
        simulator_model=custom_llm,
    )

    # Track results for this worker
    saved_files = []
    worker_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}
    test_case_count = 0

    # Generate conversations
    for i in range(num_conversations):
        conversation_number = i + 1
        worker_logger.info(
            f"[Worker {worker_id}] Generating conversation {conversation_number}/{num_conversations}"
        )

        try:
            # Get a random user ID from this worker's assigned users
            conversation_user_id = _load_random_authoritative_user_id(user_ids)
            worker_logger.info(
                f"[Worker {worker_id}] Conversation {conversation_number} using user: {conversation_user_id}"
            )

            # Create OpenShift client for this conversation
            worker_client = OpenShiftChatClient(
                conversation_user_id,
                test_script=test_script,
                reset_conversation=reset_conversation,
                message_timeout=message_timeout,
            )

            # Start session
            worker_client.start_session()
            worker_client.get_agent_initialization()

            # Create conversation golden
            conversation_golden = _create_conversation_golden(
                conversation_number, use_structured_output=use_structured_output
            )

            # Simulate conversation
            conversational_test_cases = simulator.simulate(
                conversational_goldens=[conversation_golden],
                max_user_simulations=max_turns,
            )

            # Request token summary
            try:
                if worker_client.session_active:
                    token_response = worker_client.send_message("**tokens**")
                    worker_logger.info(
                        f"[Worker {worker_id}] Token response: {token_response}"
                    )
            except Exception as e:
                worker_logger.warning(
                    f"[Worker {worker_id}] Failed to request tokens: {e}"
                )

            # Close session
            worker_client.close_session()

            # Collect tokens
            app_tokens = worker_client.get_app_tokens()
            worker_tokens["input"] += app_tokens["input"]
            worker_tokens["output"] += app_tokens["output"]
            worker_tokens["total"] += app_tokens["total"]
            worker_tokens["calls"] += app_tokens["calls"]

            # Save test cases
            for test_case in conversational_test_cases:
                test_case_count += 1
                conversation = _convert_test_case_to_conversation_format(
                    test_case, conversation_user_id
                )
                if conversation.get("conversation"):
                    base_filename = (
                        f"generated_flow_worker{worker_id}_{test_case_count}"
                    )
                    saved_file = _save_conversation_to_file(conversation, base_filename)
                    saved_files.append(saved_file)

        except Exception as e:
            worker_logger.error(
                f"[Worker {worker_id}] Error in conversation {conversation_number}: {e}",
                exc_info=True,
            )
            continue

    worker_logger.info(
        f"[Worker {worker_id}] Completed. Generated {test_case_count} test cases"
    )

    return {
        "worker_id": worker_id,
        "saved_files": saved_files,
        "tokens": worker_tokens,
        "test_case_count": test_case_count,
    }


def _convert_test_case_to_conversation_format(
    test_case: ConversationalTestCase, authoritative_user_id: str
) -> dict[str, Any]:
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
            content = turn.content

            # This handles cases where Structured Output mode saves the whole Pydantic object as a string
            if (
                isinstance(content, str)
                and content.strip().startswith("{")
                and "simulated_input" in content
            ):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and "simulated_input" in data:
                        content = str(data["simulated_input"])
                except Exception:
                    # If parsing fails, keep original content
                    pass

            conversation_turns.append({"role": turn.role, "content": content})

    return {
        "metadata": {
            "authoritative_user_id": authoritative_user_id,
            "description": "Generated conversation from deepeval simulation",
        },
        "conversation": conversation_turns,
    }


def _save_conversation_to_file(
    conversation: dict[str, Any], base_filename: str = "generated_conversation"
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

    # Get API configuration from environment variables
    api_key, api_endpoint, model_name = get_api_configuration()

    if not api_key:
        logger.error("No API key found. Set LLM_API_TOKEN environment variable.")
        exit(1)

    if not api_endpoint:
        logger.error("No API endpoint found. Set LLM_URL environment variable.")
        exit(1)

    logger.info(
        f"Starting conversation simulation with model: {model_name or 'default'}"
    )

    # Load and partition user IDs
    all_user_ids = _load_all_authoritative_user_ids()
    logger.info(f"Loaded {len(all_user_ids)} user IDs")

    # Validate concurrency doesn't exceed available users
    if args.concurrency > len(all_user_ids):
        logger.error(
            f"Concurrency ({args.concurrency}) cannot exceed number of users ({len(all_user_ids)})"
        )
        exit(1)

    # Log execution mode
    if args.concurrency > 1:
        logger.info(f"Running in CONCURRENT mode with {args.concurrency} workers")
        logger.info(
            f"Each worker will generate {args.num_conversations} conversation(s)"
        )
        logger.info(f"Total conversations: {args.concurrency * args.num_conversations}")
    else:
        logger.info("Running in SEQUENTIAL mode")
        logger.info(f"Generating {args.num_conversations} conversation(s) sequentially")
    logger.info(f"Maximum user simulations per conversation: {args.max_turns}")

    try:
        # Partition users across workers (even if only 1 worker for sequential mode)
        user_partitions = _partition_user_ids(all_user_ids, args.concurrency)
        if args.concurrency > 1:
            logger.info(f"Partitioned users into {len(user_partitions)} groups:")
            for i, partition in enumerate(user_partitions):
                logger.info(f"  Worker {i}: {len(partition)} users - {partition}")

        # Create worker arguments
        worker_args = [
            (
                i,
                user_partitions[i],
                args.num_conversations,
                args.max_turns,
                args.test_script,
                args.reset_conversation,
                args.message_timeout,
                args.use_structured_output,
            )
            for i in range(args.concurrency)
        ]

        # Run workers (in parallel or sequentially)
        if args.concurrency > 1:
            logger.info(f"Starting {args.concurrency} parallel workers...")
            with Pool(processes=args.concurrency) as pool:
                results = pool.starmap(_run_worker, worker_args)
        else:
            # Sequential mode: just run the single worker directly
            results = [_run_worker(*worker_args[0])]

        # Aggregate results from all workers
        all_saved_files = []
        total_app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}
        total_test_cases = 0

        for result in results:
            all_saved_files.extend(result["saved_files"])
            total_app_tokens["input"] += result["tokens"]["input"]
            total_app_tokens["output"] += result["tokens"]["output"]
            total_app_tokens["total"] += result["tokens"]["total"]
            total_app_tokens["calls"] += result["tokens"]["calls"]
            total_test_cases += result["test_case_count"]

        # Log completion
        mode = "Parallel" if args.concurrency > 1 else "Sequential"
        logger.info(
            f"{mode} generation completed. Generated {total_test_cases} total test cases"
        )

        # Print saved files
        if all_saved_files:
            print("\n=== Saved Conversations ===")
            for file_path in all_saved_files:
                print(f"- {file_path}")
        else:
            logger.warning("No conversation files were saved")

    except Exception as e:
        logger.error(f"Error during simulation: {e}", exc_info=True)
        exit(1)
    finally:
        # Final token summary
        from helpers.token_counter import print_token_summary

        print_token_summary(app_tokens=total_app_tokens, save_file_prefix="generator")
