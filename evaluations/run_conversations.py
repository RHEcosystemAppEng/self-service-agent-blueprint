#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from helpers.run_conversation_flow import ConversationFlowTester


def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the conversation runner."""
    parser = argparse.ArgumentParser(
        description="Run predefined conversation flows with the agent"
    )
    parser.add_argument(
        "--test-script",
        type=str,
        default=None,
        help="Name of the test script to execute (default: chat-responses-request-mgr.py, "
        "or the flow's DEFAULT_TEST_SCRIPT when --flow is used)",
    )
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Send 'reset' message at the start of each conversation",
    )
    parser.add_argument(
        "--flow",
        type=str,
        default=None,
        metavar="FLOW_NAME",
        help="Run predefined conversations for a specific flow (e.g., ticket_laptop_refresh). "
        "Uses flows/{name}/conversations/ as input and results/{name}/conversation_results/ as output.",
    )
    parser.add_argument(
        "--message-timeout",
        type=int,
        default=None,
        help="Timeout in seconds for individual message send/response operations. "
        "Default: auto — 60 for chat-responses-request-mgr.py; "
        "TRIGGER_POLL_TIMEOUT+60 (240s by default) for ticket-responses-request-mgr.py.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_arguments()

    if args.flow:
        # Flow mode: use flow-specific directories and settings
        eval_dir = str(Path(__file__).parent)
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)

        from flow_registry import get_flow_paths, load_flow

        flow_module = load_flow(args.flow)
        flow_paths = get_flow_paths(args.flow)

        conversations_dir = str(flow_paths.conversations_dir)
        output_dir = str(flow_paths.results_conv_dir)
        flow_paths.results_conv_dir.mkdir(parents=True, exist_ok=True)

        default_test_script = getattr(
            flow_module, "DEFAULT_TEST_SCRIPT", "chat-responses-request-mgr.py"
        )
        test_script = args.test_script or default_test_script
        default_reset_conversation = getattr(
            flow_module, "DEFAULT_RESET_CONVERSATION", False
        )
        reset_conversation = args.reset_conversation or default_reset_conversation
        flow_initial_message = getattr(flow_module, "DEFAULT_INITIAL_MESSAGE", None)
        flow_skip_initial = getattr(flow_module, "DEFAULT_SKIP_INITIAL_MESSAGE", False)
        flow_ticket_title = getattr(flow_module, "DEFAULT_TICKET_TITLE", None)
        flow_include_conversation_metadata = getattr(
            flow_module, "DEFAULT_INCLUDE_CONVERSATION_METADATA", False
        )
    else:
        # Default mode: existing behavior
        conversations_dir = "conversations_config/conversations"
        output_dir = "results/conversation_results"
        test_script = args.test_script or "chat-responses-request-mgr.py"
        reset_conversation = args.reset_conversation
        flow_initial_message = None
        flow_skip_initial = False
        flow_ticket_title = None
        flow_include_conversation_metadata = False

    from helpers.message_timeout import resolve_message_timeout

    message_timeout = resolve_message_timeout(test_script, args.message_timeout)

    tester = ConversationFlowTester(
        test_script=test_script,
        reset_conversation=reset_conversation,
        initial_message=flow_initial_message,
        skip_initial_message=flow_skip_initial,
        message_timeout=message_timeout,
        ticket_title=flow_ticket_title,
        include_conversation_metadata=flow_include_conversation_metadata,
    )
    tester.run_flows(conversations_dir, output_dir)
