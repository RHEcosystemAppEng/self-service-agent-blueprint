#!/usr/bin/env python3
"""
Simple CLI-based chat application with Request Manager integration.

This module provides a command-line interface for chatting with an AI agent
using the Request Manager system. It uses the shared CLIChatClient for
synchronous requests, database-backed session management, and integrated tools.
"""

import asyncio
import os

from shared_clients import CLIChatClient

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")
REQUEST_MANAGER_URL = os.environ.get("REQUEST_MANAGER_URL", "http://localhost:8080")


async def main():
    """
    Main chat application loop using the shared CLIChatClient.
    """
    chat_client = CLIChatClient(request_manager_url=REQUEST_MANAGER_URL)

    # Run the interactive chat loop
    await chat_client.chat_loop(
        initial_message="please introduce yourself and tell me how you can help",
        debug=True,  # Enable debug output
    )


if __name__ == "__main__":
    asyncio.run(main())
