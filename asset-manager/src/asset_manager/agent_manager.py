import json
import logging
from pathlib import Path

import httpx
from llama_stack_client.lib.agents.agent import AgentUtils
from llama_stack_client.types.shared.agent_config import ToolConfig, Toolgroup

from .manager import Manager


def toolgroups(agent) -> list[Toolgroup] | None:
    if not agent.get("mcp_servers") and not agent.get("knowledge_bases"):
        return None

    toolgroups: list[Toolgroup] = []
    kbs = agent.get("knowledge_bases")
    if kbs:
        toolgroups.append(
            {
                "name": "builtin::rag/knowledge_search",
                "args": {"vector_db_ids": kbs},
            }
        )

    mcp_servers = agent.get("mcp_servers")
    if mcp_servers:
        for mcp_server in mcp_servers:
            toolgroups.append("mcp::" + mcp_server)

    return toolgroups


def tool_config(agent) -> ToolConfig | None:
    if not agent.get("tool_choice"):
        return None
    return ToolConfig(tool_choice=agent["tool_choice"])


class AgentManager(Manager):
    def __init__(self, config):
        self._client = None
        self._config = config
        self._agents = []
        self._config_path = None  # Will be set when we know the config path

    def set_config_path(self, config_path: Path):
        """Set the config path so we can locate prompt files"""
        self._config_path = config_path

    def load_prompt_with_model_suffix(self, agent_name: str, model: str) -> str:
        """Load prompt file with model suffix appended to filename"""
        if not self._config_path:
            raise ValueError("Config path not set. Call set_config_path() first.")

        prompts_path = self._config_path / "prompts"

        # Extract the part after the last / from the model name
        model_suffix = model.split("/")[-1] if "/" in model else model

        # Try to load prompt with model suffix first
        prompt_with_suffix = prompts_path / f"{agent_name}-{model_suffix}.txt"

        if prompt_with_suffix.exists():
            print(f"Loading model-specific prompt: {prompt_with_suffix}")
            with open(prompt_with_suffix, "r") as f:
                return f.read()

        # Fall back to original prompt file
        original_prompt = prompts_path / f"{agent_name}.txt"
        if original_prompt.exists():
            print(f"Loading default prompt: {original_prompt}")
            with open(original_prompt, "r") as f:
                return f.read()

        print(f"No prompt file found for: {model_suffix}")
        raise FileNotFoundError(f"No prompt file found for agent {agent_name}")

    def create_agents(self):
        if self._client is None:
            self.connect_to_llama_stack()
        logging.debug("Creating agents")
        for agent in self._config["agents"]:
            self.create_agent(agent)

    def create_agent(self, agent: dict):
        # Build sampling_params from config if provided
        sampling_params = None
        if agent.get("sampling_params"):
            sampling_params = agent["sampling_params"]

        # Get the model name
        model = self.model(agent)

        # Load prompt with model suffix if config path is set, otherwise use pre-loaded instructions
        if self._config_path:
            try:
                instructions = self.load_prompt_with_model_suffix(agent["name"], model)
            except FileNotFoundError:
                # Fall back to pre-loaded instructions if no model-specific prompt found
                instructions = agent["instructions"]
        else:
            instructions = agent["instructions"]

        agent_config = AgentUtils.get_agent_config(
            model=model,
            instructions=instructions,
            tools=toolgroups(agent),
            tool_config=tool_config(agent),
            max_infer_iters=agent["max_infer_iters"],
            input_shields=agent["input_shields"],
            output_shields=agent["output_shields"],
            enable_session_persistence=agent["enable_session_persistence"],
            sampling_params=sampling_params,
        )
        agent_config["name"] = agent["name"]

        agentic_system_create_response = self._client.agents.create(
            agent_config=agent_config
        )
        return agentic_system_create_response.agent_id

    def delete_agents(self):
        if self._client is None:
            self.connect_to_llama_stack()
        logging.debug("Deleting agents")
        agents = self.agents()
        for _, agent_id in agents.items():
            self._client.agents.delete(agent_id)

    def agents(self):
        if self._client is None:
            self.connect_to_llama_stack()

        # there does not seem to be a list method available do it manually
        response = self._client.get("v1/agents", cast_to=httpx.Response)
        json_string = response.content.decode("utf-8")
        data = json.loads(json_string)

        # create dictionary with agent name as key
        agents = {}
        for agent in data["data"]:
            if isinstance(agent, dict):
                agent_id = agent.get("agent_id")
                agent_config = agent.get("agent_config", {})
                agent_name = agent_config.get(
                    "name", f"Agent_{agent_id[:8]}" if agent_id else "Unknown"
                )

                if agent_name and agent_id:
                    agents[agent_name] = agent_id

        return agents

    def model(self, agent) -> str | None:
        if agent.get("model"):
            print(agent["model"])
            return agent["model"]

        # Select the first LLM model
        if self._client is None:
            self.connect_to_llama_stack()
        models = self._client.models.list()
        model_id = next(m for m in models if m.model_type == "llm").identifier
        if model_id:
            print(model_id)
            return model_id
        return None

    def create_session(self, agent_id: str, session_name: str = None):
            """Create a new session for an agent"""
            if self._client is None:
                self.connect_to_llama_stack()
            return self._client.agents.session.create(agent_id, session_name=session_name)

    def create_agent_turn(self, agent_id: str, session_id: str, stream: bool = True, messages: list = None):
        """Send a turn to an agent"""
        if self._client is None:
            self.connect_to_llama_stack()
        return self._client.agents.turn.create(
            agent_id=agent_id,
            session_id=session_id,
            stream=stream,
            messages=messages
        )