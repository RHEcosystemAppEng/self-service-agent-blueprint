#!/usr/bin/env python3
"""
Simple CLI-based chat application with LlamaStack agent integration.

This module provides a command-line interface for chatting with an AI agent
using the LlamaStack client. It includes support for streaming responses,
session management, and integrated tools.
"""

import logging
import os
import uuid
from session_manager.session_manager import create_session_manager

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")

# remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

def main():
    """
    Main chat application loop using SessionManager.
    
    """
    # Create configured SessionManager
    session_manager = create_session_manager()
    user_id = str(uuid.uuid4())  # user ID for CLI sessions
    
    print("CLI Chat - Type 'quit' to exit, 'reset' to clear session")
    
    # Initial greeting
    kickoff_message = "please introduce yourself and tell me how you can help"
    agent_response = session_manager.handle_user_message(user_id, kickoff_message)
    print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")

    while True:
        try:
            message = input("> ")
            if message.lower() in ["quit", "exit", "q"]:
                break
            elif message.lower() == "reset":
                if session_manager.reset_user_session(user_id):
                    print("Session cleared. Starting fresh!")
                else:
                    print("No active session to clear.")
                continue
                
            if message.strip():
                # Use SessionManager to handle the message (same as Slack service)
                agent_response = session_manager.handle_user_message(user_id, message)
                print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")
                
        except KeyboardInterrupt:
            break

    print("\nbye!")


if __name__ == "__main__":
    main()
