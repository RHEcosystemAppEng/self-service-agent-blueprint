#!/usr/bin/env python3
"""
CLI chat application using ResponsesAgentManager with LangGraph state machines.

This script calls the chat.py main function with the ResponsesAgentManager
implementation for session management.
"""

from chat import main

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="CLI Chat Application using ResponsesAgentManager with LangGraph state machines"
    )
    parser.add_argument(
        "--session-name",
        "-s",
        type=str,
        help="Session name for resuming an existing conversation",
    )
    args = parser.parse_args()

    # Call main with use_responses=True to use ResponsesAgentManager
    main(use_responses=True, session_name=args.session_name)
