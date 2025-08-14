import logging
import httpx
import json

from llama_stack_client.types.shared.agent_config import (
    Toolgroup,
    ToolConfig,
)
from llama_stack_client.lib.agents.agent import AgentUtils
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

    def create_agents(self):
        if self._client is None:
            self.connect_to_llama_stack()
        logging.debug("Creating agents")
        for agent in self._config["agents"]:
            self.create_agent(agent)

    def create_agent(self, agent: dict):
        agent_config = AgentUtils.get_agent_config(
            model=self.model(agent),
            instructions=agent["instructions"],
            tools=toolgroups(agent),
            tool_config=tool_config(agent),
            max_infer_iters=agent["max_infer_iters"],
            input_shields=agent["input_shields"],
            output_shields=agent["output_shields"],
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
            return agent["model"]

        # Select the first LLM model
        if self._client is None:
            self.connect_to_llama_stack()
        models = self._client.models.list()
        model_id = next(m for m in models if m.model_type == "llm").identifier
        if model_id:
            return model_id
        return None
