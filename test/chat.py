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
from pathlib import Path
from llama_stack_client import LlamaStackClient


# remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

# Initialize client
llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
client = LlamaStackClient(
    base_url=f"http://{llama_stack_host}:8321",
    timeout=120.0,
)

# Configuration
model_id = os.environ["LLAMA_STACK_MODELS"].split(",", 1)[0]

########################
# for now create agent, will not be needed later after
# agent registration is done as part of the initialization
# Once that is in place we'll need to look up the agent_id
prompt_file = Path(__file__).resolve().parent / "prompt.txt"
system_prompt = open(prompt_file).read()

agentic_system_create_response = client.agents.create(
    agent_config={
        "model": model_id,
        "instructions": system_prompt,
        "tool_choice": "auto",
        """
        "toolgroups": [
            {
                "name": "builtin::rag/knowledge_search",
                "args": {"vector_db_ids": ["laptop-refresh-knowledge-base"]},
            },
            "mcp::asset_database",
            "mcp::servicenow",
        ],
        """
        "input_shields": [],
        "output_shields": [],
        "max_infer_iters": 10,
    }
)

agent_id = agentic_system_create_response.agent_id
##########################


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
    active_session = False
    session_id = ""
    if active_session != True:
        session_create_response = client.agents.session.create(
            agent_id, session_name=str(uuid.uuid4())
        )
        session_id = session_create_response.session_id
        print(f"Session started: {session_id}")
        active_session = True

    print("CLI Chat - Type 'quit' to exit")

    kickoff_messages = [
        {"role": "user", "content": "help me refresh my laptop my employee id is 1234"},
    ]
    agent_response = send_message_to_agent(agent_id, session_id, kickoff_messages)
    print(f"agent: {agent_response}")

    while True:
        try:
            message = input("> ")
            if message.lower() in ["quit", "exit", "q"]:
                break
            if message.strip():
                messages = []
                messages.append({"role": "user", "content": message})
                agent_response = send_message_to_agent(agent_id, session_id, messages)
                print(f"agent: {agent_response}")
        except KeyboardInterrupt:
            break

    print("\nbye!")


if __name__ == "__main__":
    main()
