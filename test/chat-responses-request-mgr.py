#!/usr/bin/env python3
"""
Simple CLI-based chat application with Request Manager integration.

This module provides a command-line interface for chatting with an AI agent
using the Request Manager system. It uses the shared CLIChatClient
for synchronous requests.
"""

import argparse
import asyncio
import os
import sys

from shared_clients import CLIChatClient

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")
REQUEST_MANAGER_URL = os.environ.get("REQUEST_MANAGER_URL", "http://localhost:8080")
USER_ID = os.environ.get("USER_ID", None)
AUTHORITATIVE_USER_ID = os.environ.get("AUTHORITATIVE_USER_ID", None)


async def main() -> None:
    """
    Main chat application loop using the shared CLIChatClient.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CLI Chat with Request Manager")
    parser.add_argument("--user-id", help="User ID for the chat session")
    parser.add_argument("--request-manager-url", help="Request Manager URL")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    # Use command line args or environment variables
    # Priority: command line arg > USER_ID env var > AUTHORITATIVE_USER_ID env var
    user_id = args.user_id or USER_ID or AUTHORITATIVE_USER_ID
    request_manager_url = args.request_manager_url or REQUEST_MANAGER_URL
    debug = args.debug

    # Create chat client with optional user_id
    chat_client = CLIChatClient(
        request_manager_url=request_manager_url,
        user_id=user_id,
    )

    if user_id:
        print(f"Using user ID: {user_id}")
    else:
        print("No user ID specified - using auto-generated UUID")

    print("Using LangGraph state machine for conversation management")

    # Interactive mode: run the chat loop (default)
    if sys.stdin.isatty():
        await chat_client.chat_loop(
            initial_message="please introduce yourself and tell me how you can help",
            debug=debug,
        )
    else:
        # Test mode: use a modified chat loop for test framework
        await chat_client.chat_loop_test_mode(
            initial_message="please introduce yourself and tell me how you can help",
            debug=debug,
        )


if __name__ == "__main__":
    asyncio.run(main())
