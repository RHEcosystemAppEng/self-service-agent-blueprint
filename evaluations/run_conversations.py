#!/usr/bin/env python3

import argparse

from helpers.run_conversation_flow import ConversationFlowTester


def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the conversation runner."""
    parser = argparse.ArgumentParser(
        description="Run predefined conversation flows with the agent"
    )
    parser.add_argument(
        "--test-script",
        type=str,
        default="chat.py",
        help="Name of the test script to execute (default: chat.py)",
    )
    parser.add_argument(
        "--no-employee-id",
        action="store_true",
        help="Use alternative conversation files from no-employee-id subdirectory",
    )
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Send 'reset' message at the start of each conversation",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_arguments()

    tester = ConversationFlowTester(
        test_script=args.test_script, reset_conversation=args.reset_conversation
    )
    tester.run_flows(
        "conversations_config/conversations",
        "results/conversation_results",
        no_employee_id=args.no_employee_id,
    )
