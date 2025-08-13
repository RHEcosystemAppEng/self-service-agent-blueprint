#!/usr/bin/env python3

import json
import logging
import os

import httpx
from llama_stack_client import LlamaStackClient

# remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

# Configuration
model_id = os.environ["LLAMA_STACK_MODELS"].split(",", 1)[0]

# Initialize client
llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
client = LlamaStackClient(
    base_url=f"http://{llama_stack_host}:8321",
    timeout=120.0,
)


def main():
    ########################
    # Print out the already registered agents
    response = client.get("v1/agents", cast_to=httpx.Response)

    json_string = response.content.decode("utf-8")
    data = json.loads(json_string)
    for agent in data["data"]:
        print(agent["agent_id"])

    ########################
    # Create the agent
    system_prompt = open("prompt.txt").read()

    agentic_system_create_response = client.agents.create(
        agent_config={
            "model": model_id,
            "instructions": system_prompt,
            "tool_choice": "auto",
            "input_shields": [],
            "output_shields": [],
            "max_infer_iters": 10,
        }
    )
    agent_id = agentic_system_create_response.agent_id
    print(agent_id)

    # Create a session that will be used to ask the agent a sequence of questions
    session_create_response = client.agents.session.create(
        agent_id, session_name="agent1"
    )
    session_id = session_create_response.session_id

    #############################
    # ASK QUESTIONS

    questions = [
        "Hello how are you doing",
    ]

    for j in range(1):
        print(
            f"Iteration {j} ------------------------------------------------------------"
        )

        for i, question in enumerate(questions):
            print("QUESTION: " + question)

            response_stream = client.agents.turn.create(
                agent_id=agent_id,
                session_id=session_id,
                stream=True,
                messages=[{"role": "user", "content": question}],
            )

            # Handle streaming response
            response = ""
            for chunk in response_stream:
                # print(chunk)
                if hasattr(chunk, "event") and hasattr(chunk.event, "payload"):
                    if chunk.event.payload.event_type == "turn_complete":
                        response = (
                            response + chunk.event.payload.turn.output_message.content
                        )

            print("  RESPONSE:" + response)


if __name__ == "__main__":
    main()
