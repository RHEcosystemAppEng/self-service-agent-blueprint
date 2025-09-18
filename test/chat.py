#!/usr/bin/env python3
"""
Simple CLI-based chat application with LlamaStack agent integration.

This module provides a command-line interface for chatting with an AI agent
using the LlamaStack client. It includes support for streaming responses,
session management, and integrated tools.
"""

import logging
import os
import sys
import uuid

from asset_manager.token_counter import (
    get_token_stats,
    print_token_summary,
)

logger = logging.getLogger(__name__)

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")

# remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)


def main(use_responses=False, session_name=None):
    """
    Main chat application loop using SessionManager.

    Args:
        use_responses (bool): If True, use ResponsesAgentManager, otherwise use AgentManager
        session_name (str): Session name for resuming existing conversation (ResponsesAgentManager only)
    """
    # Import and create configured SessionManager based on parameter
    if use_responses:
        from session_manager.session_manager_responses import (
            create_session_manager_responses,
        )

        session_manager = create_session_manager_responses(session_name=session_name)
        logger.info("Using ResponsesAgentManager with LangGraph state machines")
        if session_name:
            logger.info(f"Resuming conversation with session: {session_name}")
    else:
        from session_manager.session_manager import create_session_manager

        session_manager = create_session_manager()
        logger.info("Using AgentManager with traditional sessions")
        if session_name:
            logger.warning("session_name only supported with ResponsesAgentManager")

    # For resuming sessions, extract user_id from session name; otherwise generate new one
    if use_responses and session_name:
        # Extract user_id from session name format: session-{user_id}-{agent_name}-{unique_id}
        # User ID is a full UUID: session-{uuid}-{agent_name}-{short_uuid}
        try:
            parts = session_name.split("-")
            if len(parts) >= 7 and parts[0] == "session":
                # UUID format: 8-4-4-4-12 characters, so parts[1:6] = user_id UUID (5 segments)
                user_id = "-".join(parts[1:6])
                logger.debug(f"Resuming with user ID: {user_id}")
            else:
                user_id = str(uuid.uuid4())
                logger.debug(
                    f"Could not extract user ID from session name, using new: {user_id}"
                )
        except Exception:
            user_id = str(uuid.uuid4())
            logger.debug(f"Error parsing session name, using new user ID: {user_id}")
    else:
        user_id = str(uuid.uuid4())  # user ID for CLI sessions

    # Get authoritative user ID from environment variable if provided
    authoritative_user_id = os.environ.get("AUTHORITATIVE_USER_ID")
    if authoritative_user_id:
        logger.info(
            f"Using authoritative user ID from environment: {authoritative_user_id}"
        )

    print("CLI Chat - Type 'quit' to exit, 'reset' to clear session")

    # Only send initial greeting for new sessions, not when resuming
    if not (use_responses and session_name):
        # Initial greeting for new sessions
        kickoff_message = "please introduce yourself and tell me how you can help"
        agent_response = session_manager.handle_user_message(
            user_id, kickoff_message, authoritative_user_id
        )
        print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")
    else:
        logger.info("Resuming conversation - ready for your input.")

    while True:
        try:
            message = input("> ")
            if message.lower() in ["quit", "exit", "q"]:
                break
            elif message.lower() == "**tokens**":
                agent_response = session_manager.handle_user_message(
                    user_id, message, authoritative_user_id
                )
                print(agent_response)
                print("TOKEN_SUMMARY_END")
                sys.stdout.flush()
                break
            elif message.lower() == "reset":
                if session_manager.reset_user_session(user_id):
                    print("Session cleared. Starting fresh!")
                else:
                    print("No active session to clear.")
                continue

            if message.strip():
                # Use SessionManager to handle the message (same as Slack service)
                agent_response = session_manager.handle_user_message(
                    user_id, message, authoritative_user_id
                )
                print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")

        except KeyboardInterrupt:
            break

    print("\nbye!")

    # Show session name for resuming conversation (ResponsesAgentManager only)
    if use_responses:
        current_session_name = session_manager.get_current_session_name(user_id)
        if current_session_name:
            print(
                f"To resume this conversation, use: --session-name {current_session_name}"
            )

    # Print token usage summary for human viewing
    print("\n" + "=" * 50)
    print_token_summary(prefix="  ")
    print("=" * 50)

    # Print machine-readable token counts for parsing by callers
    stats = get_token_stats()
    print(
        f"TOKEN_SUMMARY:INPUT:{stats.total_input_tokens}:OUTPUT:{stats.total_output_tokens}:TOTAL:{stats.total_tokens}:CALLS:{stats.call_count}:MAX_SINGLE_INPUT:{stats.max_input_tokens}:MAX_SINGLE_OUTPUT:{stats.max_output_tokens}:MAX_SINGLE_TOTAL:{stats.max_total_tokens}"
    )
    print("TOKEN_SUMMARY_END")


if __name__ == "__main__":
    # Default behavior when run directly - use traditional AgentManager
    main(use_responses=False, session_name=None)
