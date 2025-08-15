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

from asset_manager.agent_manager import AgentManager
from llama_stack_client import LlamaStackClient

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")

# remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

# Initialize client
llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
client = LlamaStackClient(
    base_url=f"http://{llama_stack_host}:8321",
    timeout=120.0,
)

"""
Helper to handle streaming response
"""


def send_message_to_agent(agent_id: str, session_id: str, messages: list) -> str:
    """
    Send messages to an agent and return the response. Handle stream and
    returns full message one complete

    Args:
        agent_id: The ID of the agent to send messages to
        session_id: The session ID for the conversation
        messages: List of message dictionaries with 'role' and 'content' keys

    Returns:
        The agent's response as a string
    """
    response = ""
    response_stream = client.agents.turn.create(
        agent_id=agent_id,
        session_id=session_id,
        stream=True,
        messages=messages,
    )
    for chunk in response_stream:
        # print(chunk)
        if hasattr(chunk, "event") and hasattr(chunk.event, "payload"):
            if chunk.event.payload.event_type == "turn_complete":
                response = response + chunk.event.payload.turn.output_message.content

    return response


def main():
    """
    Main chat application loop.

    Creates a session with the agent, sends an initial kickoff message,
    and then enters an interactive loop where users can chat with the agent.
    Sessions will need to be managed in co-ordination with channel the user is
    interacting with. For now just create a session when the chat starts.
    """
    agent_manager = AgentManager({"timeout": 120})
    agents = agent_manager.agents()
    print(agents)
    agent_id = agents["routing-agent"]
    session_create_response = client.agents.session.create(
        agent_id, session_name=str(uuid.uuid4())
    )
    session_id = session_create_response.session_id
    print(f"Session started: {session_id}")

    print("CLI Chat - Type 'quit' to exit")

    kickoff_messages = [
        {
            "role": "user",
            "content": "please introduce yourself and tell me how you can help",
        },
    ]
    agent_response = send_message_to_agent(agent_id, session_id, kickoff_messages)
    print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")

    while True:
        try:
            message = input("> ")
            if message.lower() in ["quit", "exit", "q"]:
                break
            if message.strip():
                messages = []
                messages.append({"role": "user", "content": message})
                agent_response = send_message_to_agent(agent_id, session_id, messages)
                # check if we have figured out which agent to route the message to
                if agent_response.strip() in agents:
                    agent_id = agents[agent_response]
                    session_create_response = client.agents.session.create(
                        agent_id, session_name=str(uuid.uuid4())
                    )
                    session_id = session_create_response.session_id
                    agent_response = send_message_to_agent(
                        agent_id, session_id, messages
                    )
                print(f"agent: {agent_response} {AGENT_MESSAGE_TERMINATOR}")
        except KeyboardInterrupt:
            break

    print("\nbye!")


if __name__ == "__main__":
    main()
