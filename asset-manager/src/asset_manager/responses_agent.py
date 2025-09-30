import logging
import os
from pathlib import Path

import yaml
from asset_manager.util import load_config_from_path
from llama_stack_client import LlamaStackClient

logger = logging.getLogger(__name__)


class Agent:
    """
    Agent that loads configuration from agent YAML files and provides LlamaStack integration.
    (Same as original implementation)
    """

    def __init__(
        self,
        agent_name: str,
        config: dict,
        global_config: dict = None,
        system_message: str = None,
    ):
        """Initialize agent with provided configuration."""
        self.agent_name = agent_name
        self.config = config
        self.global_config = global_config or {}

        # Initialize LlamaStack client once for this agent
        llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
        timeout = self.global_config.get("timeout", 120.0)
        self.llama_client = LlamaStackClient(
            base_url=f"http://{llama_stack_host}:8321",
            timeout=timeout,
        )

        self.model = self._get_model_for_agent()
        self.default_response_config = self._get_response_config()
        self.openai_client = self._create_openai_client()
        self.system_message = system_message or self._get_default_system_message()

        # Build tools once during initialization (without authoritative_user_id)
        mcp_servers = self.config.get("mcp_servers", [])
        self.tools = self._get_mcp_tools_to_use(mcp_servers)

        logger.info(
            f"Initialized Agent '{agent_name}' with model '{self.model}' and {len(self.tools)} tools"
        )

    def _get_model_for_agent(self) -> str:
        """Get the model to use for the agent from configuration."""
        if self.config and self.config.get("model"):
            logger.info(f"Using configured model: {self.config['model']}")
            return self.config["model"]

        try:
            models = self.llama_client.models.list()
            model_id = next(m.identifier for m in models if m.model_type == "llm")
            if model_id:
                logger.info(f"Using first available LLM model: {model_id}")
                return model_id
        except Exception as e:
            logger.error(f"Error getting models from LlamaStack: {e}")

        raise RuntimeError(
            "Could not determine model from agent configuration or LlamaStack - no LLM models available"
        )

    def _get_response_config(self) -> dict:
        """Get response configuration from agent config with defaults."""
        base_config = {
            "stream": False,
            "temperature": 0.7,
        }

        if self.config and "sampling_params" in self.config:
            sampling_params = self.config["sampling_params"]
            if "strategy" in sampling_params:
                strategy = sampling_params["strategy"]
                if "temperature" in strategy:
                    base_config["temperature"] = strategy["temperature"]

        return base_config

    def _get_default_system_message(self) -> str:
        """Get default system message for the agent."""
        if self.config and self.config.get("system_message"):
            return self.config["system_message"]

        return ""

    def _create_openai_client(self):
        """Create OpenAI client pointing to LlamaStack instance."""
        import openai

        llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
        return openai.OpenAI(
            api_key="dummy-key",
            base_url=f"http://{llama_stack_host}:8321/v1/openai/v1",
            timeout=120,
        )

    def _get_vector_store_id(self, kb_name: str) -> str:
        """Get the vector store ID for a specific knowledge base."""
        try:
            vector_stores = self.openai_client.vector_stores.list()
            matching_stores = []
            for vs in vector_stores.data:
                if vs.name and kb_name in vs.name:
                    matching_stores.append(vs)

            if matching_stores:
                latest_store = max(matching_stores, key=lambda x: x.created_at)
                logger.info(
                    f"Found existing vector store: {latest_store.id} with name: {latest_store.name}"
                )
                return latest_store.id
            else:
                logger.warning(
                    f"No vector store found for knowledge base '{kb_name}', using fallback"
                )
                return kb_name

        except Exception as e:
            logger.error(
                f"Error finding vector store for knowledge base '{kb_name}': {e}"
            )
            return None

    def _get_mcp_tools_to_use(
        self,
        requested_servers: list = None,
        authoritative_user_id: str = None,
        allowed_tools: list = None,
    ) -> list:
        """Get complete tools array for LlamaStack responses API."""
        tools_to_use = []

        # Add file_search tools for knowledge bases from agent config
        knowledge_bases = self.config.get("knowledge_bases", [])
        if knowledge_bases:
            vector_store_ids = []
            for kb_name in knowledge_bases:
                vector_store_id = self._get_vector_store_id(kb_name)
                if vector_store_id:
                    vector_store_ids.append(vector_store_id)

            if vector_store_ids:
                knowledge_base_tool = {
                    "type": "file_search",
                    "vector_store_ids": vector_store_ids,
                }
                tools_to_use.append(knowledge_base_tool)

        # Add MCP tools for requested servers
        if requested_servers:
            for server_name in requested_servers:
                try:
                    # Use the existing LlamaStack client for tool lookup
                    llama_tools = self.llama_client.tools.list()
                    server_url = None
                    for tool in llama_tools:
                        if (
                            tool.provider_id == "model-context-protocol"
                            and hasattr(tool, "metadata")
                            and tool.metadata
                        ):
                            endpoint = tool.metadata.get("endpoint")
                            if endpoint:
                                from urllib.parse import urlparse

                                parsed_url = urlparse(endpoint)
                                hostname = parsed_url.hostname
                                if (
                                    hostname
                                    and f"self-service-agent-{server_name}" in hostname
                                ):
                                    server_url = endpoint
                                    break

                    mcp_tool = {
                        "type": "mcp",
                        "server_label": server_name,
                        "server_url": server_url,
                        "require_approval": "never",
                    }

                    # Add headers if authoritative_user_id is provided
                    if authoritative_user_id:
                        mcp_tool["headers"] = {
                            "AUTHORITATIVE_USER_ID": authoritative_user_id
                        }

                    # Add allowed_tools if specified
                    if allowed_tools:
                        mcp_tool["allowed_tools"] = allowed_tools

                    tools_to_use.append(mcp_tool)

                except Exception as e:
                    logger.error(
                        f"Error building MCP tool for server '{server_name}': {e}"
                    )

            logger.info(f"Built tools array with {len(tools_to_use)} tools")

        return tools_to_use

    def create_response_with_retry(
        self,
        messages: list,
        max_retries: int = 3,
        temperature: float = None,
        additional_system_messages: list = None,
        authoritative_user_id: str = None,
        allowed_tools: list = None,
    ) -> str:
        """Create a response with retry logic for empty responses and errors."""
        response = None
        last_error = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt plus retries
            try:
                response = self.create_response(
                    messages,
                    temperature=temperature,
                    additional_system_messages=additional_system_messages,
                    authoritative_user_id=authoritative_user_id,
                    allowed_tools=allowed_tools,
                )

                # Check if response is empty or contains error
                if response and response.strip():
                    # Check if it's an error message that we should retry
                    if response.startswith("Error: Unable to get response"):
                        last_error = response
                        response = ""  # Treat as empty to continue retry loop
                    else:
                        # Valid response, break out of retry loop
                        break

                # Empty response or error detected
                if attempt < max_retries:
                    retry_delay = min(
                        2**attempt, 8
                    )  # Exponential backoff: 1s, 2s, 4s, 8s max
                    logger.info(
                        f"Empty/error response on attempt {attempt + 1}/{max_retries + 1}, retrying in {retry_delay}s..."
                    )
                    import time

                    time.sleep(retry_delay)
                else:
                    logger.warning(
                        f"All {max_retries + 1} attempts failed. Last error: {last_error or 'Empty response'}"
                    )
                    response = "I apologize, but I'm having difficulty generating a response right now. Please try again."

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Exception on attempt {attempt + 1}: {e}")
                if attempt >= max_retries:
                    response = "I apologize, but I'm experiencing technical difficulties. Please try again later."
                    break

        return response

    def _check_response_errors(self, response) -> str:
        """Check for various error conditions in the LlamaStack response.

        Returns:
            str: Error description if error found, empty string if no error
        """
        try:
            # Check for explicit error field
            if hasattr(response, "error") and response.error:
                return f"Response error field: {response.error}"

            # Check for error status
            if hasattr(response, "status"):
                status = str(response.status).lower()
                if "error" in status or "fail" in status or "timeout" in status:
                    return f"Error status: {response.status}"

            # Check for tool call errors
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    if hasattr(tool_call, "error") and tool_call.error:
                        return f"Tool call error: {tool_call.error}"
                    if hasattr(tool_call, "status"):
                        status = str(tool_call.status).lower()
                        if "error" in status or "fail" in status:
                            return f"Tool call status error: {tool_call.status}"

            # Check for completion message errors
            if hasattr(response, "completion_message"):
                completion = response.completion_message
                if hasattr(completion, "error") and completion.error:
                    return f"Completion error: {completion.error}"

            # Check for output structure issues
            if hasattr(response, "output") and response.output:
                if len(response.output) == 0:
                    return "Empty output array"

                output_msg = response.output[0]
                if hasattr(output_msg, "content"):
                    if not output_msg.content or len(output_msg.content) == 0:
                        return "Empty content array in output message"

            # Check for rate limiting or quota errors
            if hasattr(response, "id") and not response.id:
                return "Missing response ID (possible rate limit or quota issue)"

            return ""  # No errors detected

        except Exception as e:
            logger.warning(f"Error while checking response errors: {e}")
            return f"Error checking failed: {e}"

    def create_response(
        self,
        messages: list,
        temperature: float = None,
        additional_system_messages: list = None,
        authoritative_user_id: str = None,
        allowed_tools: list = None,
    ) -> str:
        """Create a response using LlamaStack responses API.

        Args:
            messages: List of user/assistant messages
            temperature: Optional temperature override
            additional_system_messages: Optional list of additional system messages to include
            authoritative_user_id: Optional authoritative user ID to pass via X-LlamaStack-Provider-Data header to MCP servers
            allowed_tools: Optional list of tool names/types to restrict available tools (e.g., ['file_search', 'employee-info'])
        """
        try:
            # Start with the main system message
            messages_with_system = [{"role": "system", "content": self.system_message}]

            # Add any additional system messages
            if additional_system_messages:
                for sys_msg in additional_system_messages:
                    messages_with_system.append({"role": "system", "content": sys_msg})

            # Add the conversation messages
            messages_with_system.extend(messages)

            # Override temperature if provided
            response_config = dict(self.default_response_config)
            if temperature is not None:
                response_config["temperature"] = temperature

            # Rebuild tools if authoritative_user_id or allowed_tools is provided
            if authoritative_user_id or allowed_tools:
                mcp_servers = self.config.get("mcp_servers", [])
                tools_to_use = self._get_mcp_tools_to_use(
                    mcp_servers, authoritative_user_id, allowed_tools
                )
            else:
                tools_to_use = self.tools

            # Use the existing LlamaStack client for response creation
            response = self.llama_client.responses.create(
                input=messages_with_system,
                model=self.model,
                **response_config,
                tools=tools_to_use,
            )

            # Import token counting if available
            try:
                from asset_manager.token_counter import count_tokens_from_response

                count_tokens_from_response(
                    response, self.model, "chat_agent", messages_with_system
                )
            except ImportError:
                pass  # Token counting is optional

            # Check for error conditions in the response
            error_info = self._check_response_errors(response)
            if error_info:
                logger.warning(f"Response error detected: {error_info}")
                return ""  # Return empty to trigger retry logic

            # Extract content from LlamaStack responses API format
            try:
                if hasattr(response, "output_text"):
                    content = response.output_text
                    logger.debug(f"Extracted output_text: {content}")
                    if not content or content.strip() == "":
                        logger.warning("Empty response detected from output_text")
                        return ""  # Return empty to trigger retry logic
                    return content
                elif hasattr(response, "output") and response.output:
                    output_message = response.output[0]
                    if hasattr(output_message, "content") and output_message.content:
                        content_item = output_message.content[0]
                        if hasattr(content_item, "text"):
                            content = content_item.text
                            logger.debug(f"Extracted text content: {content}")
                            if not content or content.strip() == "":
                                logger.warning(
                                    "Empty response detected from content.text"
                                )
                                return ""  # Return empty to trigger retry logic
                            return content

                if hasattr(response, "completion_message") and hasattr(
                    response.completion_message, "content"
                ):
                    content = response.completion_message.content
                    logger.debug(f"Response content (completion_message): {content}")
                    return content
                elif hasattr(response, "content"):
                    content = response.content
                    logger.debug(f"Response content (direct): {content}")
                    return content
                elif hasattr(response, "output_text"):
                    content = response.output_text
                    logger.debug(f"Response content (output_text): {content}")
                    return content
                elif hasattr(response, "output"):
                    content = response.output
                    logger.debug(f"Response content (output): {content}")
                    return content
                elif hasattr(response, "text"):
                    content = response.text
                    logger.debug(f"Response content (text): {content}")
                    return content
                else:
                    print(
                        f"Could not extract content from response. Response attributes: {dir(response)}"
                    )
                    logger.warning(
                        f"Could not extract content from response. Response attributes: {dir(response)}"
                    )
                    logger.warning(
                        "Could not extract content from response, returning fallback message"
                    )
                    return ""  # Return empty to trigger retry logic

            except Exception as e:
                logger.error(f"Error extracting content from response: {e}")
                return f"Error processing response: {e}"

        except TimeoutError as e:
            logger.warning(f"Timeout calling LlamaStack responses API: {e}")
            return ""  # Return empty to trigger retry with longer timeout
        except ConnectionError as e:
            logger.warning(f"Connection error calling LlamaStack responses API: {e}")
            return ""  # Return empty to trigger retry
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "timeout" in error_msg
                or "connection" in error_msg
                or "network" in error_msg
            ):
                logger.warning(f"Network-related error calling LlamaStack: {e}")
                return ""  # Return empty to trigger retry
            else:
                logger.error(f"Unexpected error calling LlamaStack responses API: {e}")
                return (
                    f"Error: Unable to get response from LlamaStack responses API: {e}"
                )


class ResponsesAgentManager:
    """Manages multiple agent instances for the application."""

    def __init__(self):
        self.agents_dict = {}

        # Load the configuration from the path relative to this file
        config_path = Path(__file__).parent.parent.parent / "config"
        agent_configs = load_config_from_path(config_path)

        # Load global configuration (config.yaml)
        global_config_path = config_path / "config.yaml"
        global_config = {}
        if global_config_path.exists():
            with open(global_config_path, "r") as f:
                global_config = yaml.safe_load(f) or {}

        # Create agents for each entry in the configuration
        agents_list = agent_configs.get("agents", [])
        for agent_config in agents_list:
            agent_name = agent_config.get("name")
            if agent_name:
                # Create the agent with the loaded configuration and global config
                self.agents_dict[agent_name] = Agent(
                    agent_name, agent_config, global_config
                )

    def get_agent(self, agent_id: str):
        """Get an agent by ID, returning default if not found."""
        if agent_id in self.agents_dict:
            return self.agents_dict[agent_id]

        # If agent_id not found, return first available agent
        if self.agents_dict:
            return next(iter(self.agents_dict.values()))

        # If no agents loaded, raise an error
        raise ValueError(
            f"No agent found with ID '{agent_id}' and no agents are loaded"
        )

    def agents(self):
        """Return a dict mapping agent names to agent names (for compatibility with AgentManager)."""
        return {name: name for name in self.agents_dict.keys()}
