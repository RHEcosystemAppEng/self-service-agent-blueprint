#!/usr/bin/env python3
"""
LangGraph-based laptop refresh agent implementation using a configurable state machine.

This module implements a state machine engine that reads its configuration from
chat-lg-state.yaml, making the conversation flow easily configurable and maintainable.
"""

import logging
import os
from pathlib import Path
from typing import Annotated, Dict, List, Optional, TypedDict

import yaml
from asset_manager.util import load_config_from_path
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from llama_stack_client import LlamaStackClient

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")

# Configure logging - suppress INFO messages, only show WARNING and above
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Set this module's logger to WARNING level to suppress INFO messages
logger.setLevel(logging.WARNING)

# Remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)

# LlamaStack responses logging removed

# Initialize LlamaStack client
llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
llama_client = LlamaStackClient(
    base_url=f"http://{llama_stack_host}:8321",
    timeout=120.0,
)


class Agent:
    """
    Agent that loads configuration from agent YAML files and provides LlamaStack integration.
    (Same as original implementation)
    """

    def __init__(self, agent_name: str, system_message: str = None):
        """Initialize agent with configuration from agent YAML file."""
        self.agent_name = agent_name
        self.config = self._load_agent_config()
        self.model = self._get_model_for_agent()
        self.default_response_config = self._get_response_config()
        self.openai_client = self._create_openai_client()
        self.system_message = system_message or self._get_default_system_message()

        # Build tools once during initialization
        mcp_servers = self.config.get("mcp_servers", [])
        self.tools = self._get_mcp_tools_to_use(mcp_servers)

        logger.info(
            f"Initialized Agent '{agent_name}' with model '{self.model}' and {len(self.tools)} tools"
        )

    def _load_agent_config(self) -> dict:
        agents = load_config_from_path(Path("/app/asset-manager/config"))
        for agent in agents.get("agents", []):
            if agent.get("name") == self.agent_name:
                return agent
        raise FileNotFoundError(f"Could not load agent config for: {self.agent_name}")

    def _get_model_for_agent(self) -> str:
        """Get the model to use for the agent from configuration."""
        if self.config and self.config.get("model"):
            logger.info(f"Using configured model: {self.config['model']}")
            return self.config["model"]

        try:
            models = llama_client.models.list()
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

        return "You are a helpful laptop refresh assistant. Speak directly to users in a conversational and professional manner. CRITICAL do not share your internal thinking"

    def _create_openai_client(self):
        """Create OpenAI client pointing to LlamaStack instance."""
        import openai

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

    def _get_mcp_tools_to_use(self, requested_servers: list = None) -> list:
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
                    llama_tools = llama_client.tools.list()
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
                    tools_to_use.append(mcp_tool)

                except Exception as e:
                    logger.error(
                        f"Error building MCP tool for server '{server_name}': {e}"
                    )

            logger.info(f"Built tools array with {len(tools_to_use)} tools")

        return tools_to_use

    def create_response_with_retry(
        self, messages: list, max_retries: int = 3, temperature: float = None
    ) -> str:
        """Create a response with retry logic for empty responses and errors."""
        response = None
        last_error = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt plus retries
            try:
                response = self.create_response(messages, temperature=temperature)

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

    def create_response(self, messages: list, temperature: float = None) -> str:
        """Create a response using LlamaStack responses API."""
        try:
            messages_with_system = [
                {"role": "system", "content": self.system_message}
            ] + messages

            logger.debug(f"Using model: {self.model}")
            logger.debug(f"Using tools for responses API: {self.tools}")

            logger.debug(
                f"Calling LlamaStack with {len(messages_with_system)} messages"
            )

            # Override temperature if provided
            response_config = dict(self.default_response_config)
            if temperature is not None:
                response_config["temperature"] = temperature
                logger.debug(f"Using custom temperature: {temperature}")

            response = llama_client.responses.create(
                input=messages_with_system,
                model=self.model,
                **response_config,
                tools=self.tools,
            )

            logger.debug(f"Received response from LlamaStack: {type(response)}")

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


# Dynamic state definition created from YAML configuration
def create_agent_state_class(state_schema: dict):
    """Create a dynamic AgentState TypedDict class based on YAML configuration."""
    # Collect all field definitions
    fields = {}

    # Add system fields
    system_fields = state_schema.get("system_fields", {})
    for field_name, field_config in system_fields.items():
        field_type = field_config.get("type", "string")

        if field_name == "messages":
            # Special handling for messages field (required for LangGraph)
            fields["messages"] = Annotated[List[BaseMessage], add_messages]
        elif field_type == "string":
            fields[field_name] = str
        elif field_type == "list":
            fields[field_name] = List[Dict]
        elif field_type == "dict":
            fields[field_name] = Dict
        elif field_type == "boolean":
            fields[field_name] = bool
        else:
            fields[field_name] = str  # Default to string

    # Add business fields
    business_fields = state_schema.get("business_fields", {})
    for field_name, field_config in business_fields.items():
        field_type = field_config.get("type", "string")

        if field_type == "string":
            fields[field_name] = Optional[str]
        elif field_type == "list":
            fields[field_name] = List[Dict]
        elif field_type == "dict":
            fields[field_name] = Optional[Dict]
        elif field_type == "boolean":
            fields[field_name] = Optional[bool]
        else:
            fields[field_name] = Optional[str]  # Default to optional string

    # Create the TypedDict class dynamically
    return TypedDict("AgentState", fields)


# AgentState will be created dynamically after loading configuration


class StateMachine:
    """Configurable state machine engine for conversation flows."""

    def __init__(self, config_path: str):
        """Initialize the state machine with configuration from YAML file."""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.agent = None  # Lazy initialization

        # Create dynamic AgentState class from configuration
        state_schema = self.config.get("state_schema", {})
        self.AgentState = create_agent_state_class(state_schema)

    def _load_config(self) -> dict:
        """Load state machine configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load state machine config from {self.config_path}: {e}"
            )

    def _get_agent(self) -> Agent:
        """Get the LlamaStack agent, creating it lazily if needed."""
        if self.agent is None:
            settings = self.config.get("settings", {})
            agent_name = settings.get("agent_name", "laptop-refresh")
            system_msg = "You are a helpful laptop refresh assistant. Speak directly to users in a conversational and professional manner. CRITICAL do not share your internal thinking"
            self.agent = Agent(agent_name, system_msg)
        return self.agent

    def _get_retry_count(self) -> int:
        """Get the configured retry count for empty responses."""
        settings = self.config.get("settings", {})
        return settings.get("empty_response_retry_count", 3)

    def _format_text(self, text: str, state_data: dict) -> str:
        """Format text by replacing placeholders with state data."""
        import re

        try:
            # Add special computed values
            format_data = dict(state_data)

            # Add last_user_message placeholder
            messages = state_data.get("messages", [])
            last_user_message = ""
            for msg in reversed(messages):
                if (
                    hasattr(msg, "content")
                    and getattr(msg, "__class__", None).__name__ == "HumanMessage"
                ):
                    last_user_message = msg.content
                    break
            format_data["last_user_message"] = last_user_message

            # Custom dot notation replacement
            def replace_placeholders(text, data):
                # First, temporarily replace escaped braces to protect them
                text = text.replace("{{", "\x00ESCAPED_OPEN\x00")
                text = text.replace("}}", "\x00ESCAPED_CLOSE\x00")

                # Pattern to match {field.subfield} or {field} (but not escaped ones)
                pattern = r"\{([^}]+)\}"

                def replacer(match):
                    field_path = match.group(1)
                    try:
                        # Split by dots and navigate the data structure
                        value = data
                        for part in field_path.split("."):
                            if isinstance(value, dict):
                                value = value[part]
                            else:
                                value = getattr(value, part)
                        return str(value)
                    except (KeyError, AttributeError, TypeError):
                        # Return the placeholder unchanged if field not found
                        logger.warning(f"Missing placeholder data for {field_path}")
                        return match.group(0)

                # Replace placeholders
                text = re.sub(pattern, replacer, text)

                # Restore escaped braces as single braces
                text = text.replace("\x00ESCAPED_OPEN\x00", "{")
                text = text.replace("\x00ESCAPED_CLOSE\x00", "}")

                return text

            return replace_placeholders(text, format_data)

        except Exception as e:
            logger.warning(f"Error formatting text: {e}, returning original text")
            return text

    def process_llm_processor_state(self, state: dict, state_config: dict) -> dict:
        """Process llm_processor type states - completely generic and configuration-driven."""

        # Step 1: Determine the prompt to use
        prompt = self._get_prompt_for_state(state, state_config)

        # Step 2: Send prompt to LLM and get response with retry logic for empty responses
        messages_to_send = [{"role": "user", "content": prompt}]
        temperature = state_config.get(
            "temperature"
        )  # Get temperature from state config
        response = self._get_agent().create_response_with_retry(
            messages_to_send, self._get_retry_count(), temperature=temperature
        )

        # Step 3: Store response data as configured
        self._store_response_data(state, state_config, response)

        # Step 4: Add response to conversation
        state["messages"].append(AIMessage(content=response))

        # Step 5: Analyze response and determine next state
        next_state = self._analyze_response_and_transition(
            state, state_config, response
        )
        state["current_state"] = next_state

        return state

    def _get_prompt_for_state(self, state: dict, state_config: dict) -> str:
        """Get the appropriate prompt based on conditional logic or default."""

        # Check for conditional prompts
        conditional_prompts = state_config.get("conditional_prompts")
        if conditional_prompts:
            for condition_config in conditional_prompts:
                condition_name = condition_config.get("condition")

                if condition_name == "default":
                    continue  # Handle default last

                # Check if condition is met
                if self._evaluate_condition(state, condition_config):
                    prompt_text = condition_config.get("prompt", "")
                    return self._format_text(prompt_text, state)

            # If no conditions matched, use default
            for condition_config in conditional_prompts:
                if condition_config.get("condition") == "default":
                    prompt_text = condition_config.get("prompt", "")
                    return self._format_text(prompt_text, state)

        # Fallback to simple prompt
        prompt_text = state_config.get("prompt", "")
        return self._format_text(prompt_text, state)

    def _evaluate_condition(self, state: dict, condition_config: dict) -> bool:
        """Evaluate whether a condition is met based on state data."""
        check_field = condition_config.get("check_field")
        check_phrases = condition_config.get("check_phrases", [])
        check_empty = condition_config.get("check_empty")

        # Handle empty/non-empty checks
        if check_field and check_empty is not None:
            field_value = self._get_nested_field_value(state, check_field)
            if check_empty:
                # Check if field is empty (None, empty list, empty string)
                return not field_value or (
                    isinstance(field_value, (list, str)) and len(field_value) == 0
                )
            else:
                # Check if field is not empty
                return bool(
                    field_value
                    and (
                        not isinstance(field_value, (list, str)) or len(field_value) > 0
                    )
                )

        # Handle phrase-based checks
        if not check_field or not check_phrases:
            return False

        # Navigate to the field value (supports dot notation like "laptop_eligibility.response")
        field_value = self._get_nested_field_value(state, check_field)
        if not field_value:
            return False

        # Check if any of the phrases are present
        field_value_lower = str(field_value).lower()
        return any(phrase.lower() in field_value_lower for phrase in check_phrases)

    def _get_nested_field_value(self, state: dict, field_path: str):
        """Get a nested field value using dot notation (e.g., 'laptop_eligibility.response')."""
        try:
            value = state
            for part in field_path.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
            return value
        except (KeyError, TypeError, AttributeError):
            return None

    def _store_response_data(self, state: dict, state_config: dict, response: str):
        """Store response data according to configuration."""
        data_storage = state_config.get("data_storage", {})
        for key, source in data_storage.items():
            if source == "llm_response":
                state[key] = {"response": response}

    def _analyze_response_and_transition(
        self, state: dict, state_config: dict, response: str
    ) -> str:
        """Analyze LLM response and determine next state transition."""

        # Check for response analysis configuration
        response_analysis = state_config.get("response_analysis")
        if response_analysis:
            return self._process_response_analysis(state, response_analysis, response)

        # Fallback to simple transitions
        transitions = state_config.get("transitions", {})
        return transitions.get("success", "end")

    def _process_response_analysis(
        self, state: dict, analysis_config: dict, response: str
    ) -> str:
        """Process response analysis with conditions and actions."""
        response_lower = response.lower()

        conditions = analysis_config.get("conditions", [])
        for condition in conditions:
            trigger_phrases = condition.get("trigger_phrases", [])
            exclude_phrases = condition.get("exclude_phrases", [])

            # Check if trigger phrases are present
            has_trigger = any(
                phrase.lower() in response_lower for phrase in trigger_phrases
            )
            if not has_trigger:
                continue

            # Check if exclude phrases are present (if so, skip this condition)
            has_exclude = any(
                phrase.lower() in response_lower for phrase in exclude_phrases
            )
            if has_exclude:
                continue

            # Execute actions for this condition - completely generic
            actions = condition.get("actions", [])
            next_state = self._execute_actions(state, actions, response, response_lower)

            if next_state:
                return next_state

        # If no conditions matched, use default transition
        return analysis_config.get("default_transition", "end")

    def _execute_actions(
        self, state: dict, actions: list, response: str, response_lower: str
    ) -> str:
        """Execute a list of actions completely generically based on configuration."""
        next_state = None

        for action in actions:
            action_type = action.get("type")

            if action_type == "transition":
                next_state = action.get("target", "end")

            elif action_type == "check_correction":
                # Check if correction is needed based on phrases
                correction_phrases = action.get("correction_phrases", [])
                if any(
                    phrase.lower() in response_lower for phrase in correction_phrases
                ):
                    correction_message = action.get("correction_message", "")
                    if correction_message:
                        formatted_message = self._format_text(correction_message, state)
                        state["messages"].append(AIMessage(content=formatted_message))

            elif action_type == "extract_data":
                # Generic data extraction using regex patterns
                pattern = action.get("pattern", "")
                field_name = action.get("field_name", "")
                source_text = action.get(
                    "source", "response"
                )  # "response" or "last_user_message"

                if pattern and field_name:
                    import re

                    if source_text == "response":
                        text_to_search = response
                    elif source_text == "last_user_message":
                        text_to_search = self._get_last_user_message(state)
                    else:
                        text_to_search = response

                    match = re.search(pattern, text_to_search)
                    if match:
                        # Use group(1) if available (captured group), otherwise group(0) (entire match)
                        try:
                            state[field_name] = match.group(1)
                        except IndexError:
                            state[field_name] = match.group(0)

            elif action_type == "add_message":
                # Add a message to the conversation
                message_content = action.get("message", "")
                if message_content:
                    formatted_message = self._format_text(message_content, state)
                    state["messages"].append(AIMessage(content=formatted_message))

            elif action_type == "set_field":
                # Set a field value
                field_name = action.get("field_name", "")
                field_value = action.get("value")
                if field_name:
                    state[field_name] = field_value

        return next_state

    def _get_last_user_message(self, state: dict) -> str:
        """Get the last user message from the conversation."""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if (
                hasattr(msg, "content")
                and getattr(msg, "__class__", None).__name__ == "HumanMessage"
            ):
                return msg.content
        return ""

    def is_terminal_state(self, state_name: str) -> bool:
        """Check if the given state is a terminal state."""
        settings = self.config.get("settings", {})
        terminal_state = settings.get("terminal_state", "end")
        return state_name == terminal_state

    def is_waiting_state(self, state_name: str) -> bool:
        """Check if the given state is a waiting state."""
        settings = self.config.get("settings", {})
        waiting_prefix = settings.get("waiting_state_prefix", "waiting_")
        return state_name.startswith(waiting_prefix)

    def remove_waiting_prefix(self, state_name: str) -> str:
        """Remove the waiting prefix from a state name."""
        settings = self.config.get("settings", {})
        waiting_prefix = settings.get("waiting_state_prefix", "waiting_")
        if state_name.startswith(waiting_prefix):
            return state_name.replace(waiting_prefix, "", 1)
        return state_name

    def create_initial_state(self) -> dict:
        """Create initial state with default field values from configuration."""
        settings = self.config.get("settings", {})
        initial_state_name = settings.get("initial_state", "collect_employee_id")
        state_schema = self.config.get("state_schema", {})

        # Create state with default values from schema
        state = {}

        # Add system fields
        system_fields = state_schema.get("system_fields", {})
        for field_name, field_config in system_fields.items():
            default_value = field_config.get("default")
            if field_name == "current_state":
                state[field_name] = initial_state_name
            elif default_value == "null" or default_value is None:
                if field_config.get("type") == "list":
                    state[field_name] = []
                else:
                    state[field_name] = None
            else:
                state[field_name] = default_value

        # Add business fields
        business_fields = state_schema.get("business_fields", {})
        for field_name, field_config in business_fields.items():
            default_value = field_config.get("default")
            if default_value == "null" or default_value is None:
                if field_config.get("type") == "list":
                    state[field_name] = []
                else:
                    state[field_name] = None
            elif default_value == "false":
                state[field_name] = False
            elif default_value == "true":
                state[field_name] = True
            else:
                state[field_name] = default_value

        return state

    def reset_state_for_new_conversation(self) -> dict:
        """Reset state for a new conversation based on end state configuration."""
        end_state_config = self.config.get("states", {}).get("end", {})
        reset_behavior = end_state_config.get("reset_behavior", {})
        settings = self.config.get("settings", {})
        state_schema = self.config.get("state_schema", {})

        # Get reset state name
        reset_state = reset_behavior.get(
            "reset_state",
            f"{settings.get('waiting_state_prefix', 'waiting_')}{settings.get('initial_state', 'collect_employee_id')}",
        )

        # Get fields to clear from reset behavior or use all fields
        fields_to_clear = reset_behavior.get("clear_data", [])
        if not fields_to_clear:
            # If no specific fields listed, clear all fields
            all_fields = list(state_schema.get("system_fields", {}).keys()) + list(
                state_schema.get("business_fields", {}).keys()
            )
            fields_to_clear = all_fields

        # Create new state using schema defaults
        state = {}

        # Reset system fields
        system_fields = state_schema.get("system_fields", {})
        for field_name in fields_to_clear:
            if field_name in system_fields:
                field_config = system_fields[field_name]
                if field_name == "current_state":
                    state[field_name] = reset_state
                elif field_config.get("type") == "list":
                    state[field_name] = []
                else:
                    state[field_name] = None

        # Reset business fields
        business_fields = state_schema.get("business_fields", {})
        for field_name in fields_to_clear:
            if field_name in business_fields:
                field_config = business_fields[field_name]
                default_value = field_config.get("default")
                if default_value == "false":
                    state[field_name] = False
                elif default_value == "true":
                    state[field_name] = True
                elif field_config.get("type") == "list":
                    state[field_name] = []
                else:
                    state[field_name] = None

        return state

    def process_intent_classifier_state(self, state: dict, state_config: dict) -> dict:
        """Process intent_classifier type states."""
        messages = state["messages"]
        last_message = messages[-1] if messages else None

        if not last_message or not isinstance(last_message, HumanMessage):
            state["current_state"] = f"waiting_{state['current_state']}"
            return state

        user_input = last_message.content.strip()

        # Use LLM to classify intent
        intent_prompt = self._format_text(
            state_config.get("intent_prompt", ""), {**state, "user_input": user_input}
        )
        intent_messages = [{"role": "user", "content": intent_prompt}]
        temperature = state_config.get(
            "temperature"
        )  # Get temperature from state config
        intent_response = (
            self._get_agent()
            .create_response_with_retry(
                intent_messages, self._get_retry_count(), temperature=temperature
            )
            .strip()
            .upper()
        )

        # Process intent actions
        intent_actions = state_config.get("intent_actions", {})
        for intent_name, action in intent_actions.items():
            if isinstance(intent_name, str) and intent_name in intent_response:
                # Handle response
                if "response" in action:
                    response = self._format_text(
                        action["response"], {**state, "user_input": user_input}
                    )
                    state["messages"].append(AIMessage(content=response))

                # Handle LLM prompt
                if "prompt" in action:
                    prompt = self._format_text(
                        action["prompt"], {**state, "user_input": user_input}
                    )
                    messages_to_send = [{"role": "user", "content": prompt}]
                    # Use state temperature for intent action prompts for consistency
                    action_temperature = state_config.get(
                        "temperature", 0.6
                    )  # Fallback to 0.6
                    response = self._get_agent().create_response_with_retry(
                        messages_to_send,
                        self._get_retry_count(),
                        temperature=action_temperature,
                    )
                    state["messages"].append(AIMessage(content=response))

                # Handle data storage
                if "data_storage" in action:
                    for key, value in action["data_storage"].items():
                        # Format the value to substitute placeholders like {user_input}
                        formatted_value = self._format_text(
                            str(value), {**state, "user_input": user_input}
                        )
                        state[key] = formatted_value

                # Handle state transition
                if "next_state" in action:
                    state["current_state"] = action["next_state"]

                return state

        # Default fallback if no intent matched
        state["current_state"] = f"waiting_{state['current_state']}"
        return state

    def process_llm_validator_state(self, state: dict, state_config: dict) -> dict:
        """Process llm_validator type states (like laptop selection validation)."""
        messages = state["messages"]
        last_message = messages[-1] if messages else None

        if not last_message or not isinstance(last_message, HumanMessage):
            return state

        user_input = last_message.content.strip()

        # Use LLM to validate the input
        # Add user_input to state for formatting
        format_state = dict(state)
        format_state["user_input"] = user_input
        validation_prompt = self._format_text(
            state_config.get("validation_prompt", ""), format_state
        )

        # Build conversation context
        messages_to_send = []
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                messages_to_send.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages_to_send.append({"role": "assistant", "content": msg.content})

        messages_to_send.append({"role": "system", "content": validation_prompt})
        temperature = state_config.get("temperature", 0.3)  # Default for validation
        response = self._get_agent().create_response_with_retry(
            messages_to_send, self._get_retry_count(), temperature=temperature
        )

        # Use LLM to determine if validation passed
        success_validation_prompt = self._format_text(
            state_config.get("success_validation_prompt", ""),
            {"llm_response": response},
        )
        validation_messages = [{"role": "user", "content": success_validation_prompt}]
        validation_response = (
            self._get_agent()
            .create_response_with_retry(
                validation_messages,
                self._get_retry_count(),
                temperature=0.1,  # Very deterministic for validation classification
            )
            .strip()
            .upper()
        )

        # Store data and transition
        data_storage = state_config.get("data_storage", {})
        for key, source in data_storage.items():
            if source == "user_input":
                state[key] = user_input

        transitions = state_config.get("transitions", {})
        if "VALID" in validation_response:
            state["current_state"] = transitions.get("valid", "end")
        else:
            state["current_state"] = transitions.get(
                "invalid", "waiting_laptop_selection"
            )

        state["messages"].append(AIMessage(content=response))
        return state

    def process_terminal_state(self, state: dict, state_config: dict) -> dict:
        """Process terminal type states."""
        state["current_state"] = "end"
        return state

    def process_state(self, state: dict) -> dict:
        """Process the current state based on its configuration."""
        current_state_name = state.get("current_state", "")

        # Handle waiting states by removing "waiting_" prefix
        if current_state_name.startswith("waiting_"):
            base_state_name = current_state_name.replace("waiting_", "")
            if base_state_name in self.config["states"]:
                current_state_name = base_state_name

        state_config = self.config["states"].get(current_state_name)
        if not state_config:
            logger.error(f"Unknown state: {current_state_name}")
            state["current_state"] = "end"
            return state

        state_type = state_config.get("type", "")

        if state_type == "llm_processor":
            return self.process_llm_processor_state(state, state_config)
        elif state_type == "intent_classifier":
            return self.process_intent_classifier_state(state, state_config)
        elif state_type == "llm_validator":
            return self.process_llm_validator_state(state, state_config)
        elif state_type == "terminal":
            return self.process_terminal_state(state, state_config)
        else:
            logger.error(f"Unknown state type: {state_type}")
            state["current_state"] = "end"
            return state


# Create global state machine instance
try:
    config_path = Path(__file__).parent / "chat-lg-state.yaml"
except NameError:
    # Handle case when __file__ is not defined (e.g., when executed via exec())
    config_path = Path("/tmp/chat-lg-state.yaml")
state_machine = StateMachine(config_path)


# Main dispatcher function
def dispatcher(state: dict) -> dict:
    """Main dispatcher that processes states using the state machine."""
    logger.info(f"Dispatcher called with current_state: {state.get('current_state')}")
    return state_machine.process_state(state)


# Routing function
def route_next_step(state: dict) -> str:
    """Route to the next step based on current state - completely configuration-driven."""
    settings = state_machine.config.get("settings", {})
    current_state = state.get(
        "current_state", settings.get("initial_state", "collect_employee_id")
    )

    # Terminal state
    if state_machine.is_terminal_state(current_state):
        return END

    # Waiting states end (wait for user input)
    if state_machine.is_waiting_state(current_state):
        return END

    # All other states continue to dispatcher
    return "dispatcher"


# Create the graph
def create_laptop_refresh_graph() -> StateGraph:
    """Create and configure the LangGraph for laptop refresh workflow."""
    # Use the dynamic AgentState from the state machine
    workflow = StateGraph(state_machine.AgentState)

    # Add single dispatcher node
    workflow.add_node("dispatcher", dispatcher)

    # Set entry point
    workflow.set_entry_point("dispatcher")

    # Add conditional routing from dispatcher
    workflow.add_conditional_edges(
        "dispatcher",
        route_next_step,
        {
            "dispatcher": "dispatcher",
            END: END,
        },
    )

    return workflow.compile(debug=False)


def main():
    """Main function to run the configurable state machine laptop refresh agent."""
    print("=== Configurable LangGraph Laptop Refresh Agent ===")
    print("This agent uses a YAML-configured state machine with LlamaStack")
    print("Type 'quit' to exit")
    print("-" * 50)

    # Create the graph
    app = create_laptop_refresh_graph()

    # Initial state - completely configuration-driven
    initial_state = state_machine.create_initial_state()

    # Run the initial step
    try:
        logger.info("Starting initial invocation of the graph")
        result = app.invoke(initial_state)
        logger.info(
            f"Initial invocation completed, result state: {result.get('current_state')}"
        )

        # Print initial response
        if result["messages"]:
            print(
                f"\nagent: {result['messages'][-1].content} {AGENT_MESSAGE_TERMINATOR}"
            )
        else:
            print("\nNo response received from agent")

        # Interactive loop
        while True:
            try:
                user_input = input("\n> ")
                if user_input.lower() in ["quit", "exit", "q"]:
                    break

                if user_input.strip():
                    # Add user message to state
                    result["messages"].append(HumanMessage(content=user_input))

                    # Reset current_state to continue processing based on current state
                    current_state = result.get("current_state")
                    if state_machine.is_waiting_state(current_state):
                        # Use standard transition mechanism for waiting states
                        states_config = state_machine.config.get("states", {})
                        if current_state in states_config:
                            state_config = states_config[current_state]
                            transitions = state_config.get("transitions", {})
                            next_state = transitions.get("user_input", current_state)
                            result["current_state"] = next_state

                    # Continue the conversation
                    result = app.invoke(result)

                    # Print agent response
                    if result["messages"] and len(result["messages"]) > 0:
                        last_message = result["messages"][-1]
                        if isinstance(last_message, AIMessage):
                            print(
                                f"\nagent: {last_message.content} {AGENT_MESSAGE_TERMINATOR}"
                            )

                    # Check if conversation ended
                    if state_machine.is_terminal_state(result.get("current_state")):
                        print("\n" + "=" * 50)
                        print("Conversation completed!")
                        print("Starting new conversation...")
                        print("=" * 50)

                        # Reset state for next conversation - completely configuration-driven
                        result = state_machine.reset_state_for_new_conversation()

            except KeyboardInterrupt:
                break

    except Exception as e:
        print(f"Error running agent: {e}")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
