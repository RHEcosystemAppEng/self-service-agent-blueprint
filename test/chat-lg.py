#!/usr/bin/env python3
"""
LangGraph-based laptop refresh agent implementation.

This module implements a LangGraph agent that handles the laptop refresh workflow
with 4 main nodes: employee ID collection, eligibility check, laptop selection,
and ServiceNow ticket confirmation.

Uses LlamaStack's responses API directly instead of the agent system.
Tools are already registered with the LlamaStack instance.
"""

import logging
import os
from pathlib import Path
from typing import Annotated, Dict, List, Optional, TypedDict

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

# Initialize LlamaStack client
llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
llama_client = LlamaStackClient(
    base_url=f"http://{llama_stack_host}:8321",
    timeout=120.0,
)


class Agent:
    """
    Agent that loads configuration from agent YAML files and provides LlamaStack integration.
    """

    def __init__(self, agent_name: str, system_message: str = None):
        """
        Initialize agent with configuration from agent YAML file.

        Args:
            agent_name: Name of the agent (should match YAML filename without extension)
            system_message: Default system message to include in all conversations
        """
        self.agent_name = agent_name
        self.config = self._load_agent_config()
        self.model = self._get_model_for_agent()
        self.default_response_config = self._get_response_config()
        self.openai_client = self._create_openai_client()

        # Set default system message
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
        # Check if model is specified in agent config
        if self.config and self.config.get("model"):
            logger.info(f"Using configured model: {self.config['model']}")
            return self.config["model"]

        # Select the first LLM model from LlamaStack (fallback behavior)
        try:
            models = llama_client.models.list()
            model_id = next(m.identifier for m in models if m.model_type == "llm")
            if model_id:
                logger.info(f"Using first available LLM model: {model_id}")
                return model_id
        except Exception as e:
            logger.error(f"Error getting models from LlamaStack: {e}")

        # Throw exception if no model can be determined
        raise RuntimeError(
            "Could not determine model from agent configuration or LlamaStack - no LLM models available"
        )

    def _get_response_config(self) -> dict:
        """Get response configuration from agent config with defaults."""
        base_config = {
            "stream": False,
            "temperature": 0.7,
            # Note: LlamaStack responses API only supports stream and temperature
        }

        # Override with sampling params from agent config if present
        if self.config and "sampling_params" in self.config:
            sampling_params = self.config["sampling_params"]

            if "strategy" in sampling_params:
                strategy = sampling_params["strategy"]
                if "temperature" in strategy:
                    base_config["temperature"] = strategy["temperature"]
                # Skip top_p and max_tokens as they're not supported by responses API

        return base_config

    def _get_default_system_message(self) -> str:
        """Get default system message for the agent."""
        # Check if system message is specified in agent config
        if self.config and self.config.get("system_message"):
            return self.config["system_message"]

        # Default system message for laptop refresh agent
        return "You are a helpful laptop refresh assistant. Speak directly to users in a conversational and professional manner. Help them with their laptop refresh requests by looking up their information, checking eligibility, showing options, and creating tickets as needed."

    def _create_openai_client(self):
        """Create OpenAI client pointing to LlamaStack instance."""
        import openai

        return openai.OpenAI(
            api_key="dummy-key",  # LlamaStack doesn't require real API key
            base_url=f"http://{llama_stack_host}:8321/v1/openai/v1",  # Point to LlamaStack OpenAI v1 endpoints
        )

    def _get_vector_store_id(self, kb_name: str) -> str:
        """
        Get the vector store ID for a specific knowledge base.

        Args:
            kb_name: Name of the knowledge base to get vector store ID for

        Returns:
            The vector store ID to use for file_search tools
        """
        # For OpenAI API file_search, we need to find the vector store created by asset manager
        # The asset manager creates vector stores via OpenAI API with unique names
        # We'll try to find the most recent vector store for this knowledge base
        try:
            vector_stores = self.openai_client.vector_stores.list()

            # Look for vector stores that match our knowledge base name pattern
            matching_stores = []
            for vs in vector_stores.data:
                if vs.name and kb_name in vs.name:
                    matching_stores.append(vs)

            if matching_stores:
                # Use the most recently created vector store
                latest_store = max(matching_stores, key=lambda x: x.created_at)
                logger.info(
                    f"Found existing vector store: {latest_store.id} with name: {latest_store.name}"
                )
                return latest_store.id
            else:
                logger.warning(
                    f"No vector store found for knowledge base '{kb_name}', using fallback"
                )
                return kb_name  # Fallback to knowledge base name

        except Exception as e:
            logger.error(
                f"Error finding vector store for knowledge base '{kb_name}': {e}"
            )
            return None

    def _get_mcp_tools_to_use(self, requested_servers: list = None) -> list:
        """
        Get complete tools array for LlamaStack responses API.

        Args:
            requested_servers: List of MCP server names to include (if None, will use all servers from agent config)

        Returns:
            Complete tools array ready for llama_client.responses.create()
        """
        tools_to_use = []

        # Add file_search tools for knowledge bases from agent config
        knowledge_bases = self.config.get("knowledge_bases", [])
        if knowledge_bases:
            # Get vector store IDs for each knowledge base
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
                    # Get all tools from LlamaStack to find server URL
                    llama_tools = llama_client.tools.list()

                    # Look for any tool from this MCP server to get the URL
                    server_url = None
                    for tool in llama_tools:
                        if (
                            tool.provider_id == "model-context-protocol"
                            and hasattr(tool, "metadata")
                            and tool.metadata
                        ):

                            # Extract server URL from metadata
                            endpoint = tool.metadata.get("endpoint")
                            if endpoint:
                                # Check if this endpoint matches our server name
                                from urllib.parse import urlparse

                                parsed_url = urlparse(endpoint)
                                hostname = parsed_url.hostname
                                if (
                                    hostname
                                    and f"self-service-agent-{server_name}" in hostname
                                ):
                                    server_url = endpoint
                                    break

                    # Add MCP tool for this server
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

            return ""  # No errors detected

        except Exception as e:
            logger.warning(f"Error while checking response errors: {e}")
            return f"Error checking failed: {e}"

    def create_response(self, messages: list, temperature: float = None) -> str:
        """
        Create a response using LlamaStack responses API.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys

        Returns:
            The model's response as a string
        """
        try:
            # Prepend system message to the conversation
            messages_with_system = [
                {"role": "system", "content": self.system_message}
            ] + messages

            logger.debug(f"Using model: {self.model}")
            logger.debug(f"Using tools for responses API: {self.tools}")

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

            # Handle response - tools execute automatically with responses API
            logger.debug(f"Response object: {response}")
            logger.debug(f"Response type: {type(response)}")

            # Check for error conditions in the response
            error_info = self._check_response_errors(response)
            if error_info:
                logger.warning(f"Response error detected: {error_info}")
                return ""  # Return empty to trigger retry logic

            # Extract content from LlamaStack responses API format
            try:
                # Check for the new response format
                if hasattr(response, "output_text") and response.output_text:
                    content = response.output_text
                    logger.debug(f"Extracted output_text: {content}")
                    return content
                elif hasattr(response, "output") and response.output:
                    # Get the first output message
                    output_message = response.output[0]
                    if hasattr(output_message, "content") and output_message.content:
                        # Get the first content item
                        content_item = output_message.content[0]
                        if hasattr(content_item, "text"):
                            content = content_item.text
                            logger.debug(f"Extracted text content: {content}")
                            return content

                # Fallback attempts
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
                else:
                    logger.warning(
                        f"Could not extract content from response. Response attributes: {dir(response)}"
                    )
                    return ""  # Return empty to trigger retry logic

            except Exception as e:
                logger.error(f"Error extracting content from response: {e}")
                return ""  # Return empty to trigger retry logic

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


# Create global agent instance with system message
system_msg = "You are a helpful laptop refresh assistant. Speak directly to users in a conversational and professional manner. CRITICAL do not share your internal thinking"
laptop_refresh_agent = Agent("laptop-refresh", system_msg)


# State definition for the LangGraph
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    employee_id: Optional[str]
    employee_info: Optional[Dict]
    laptop_eligibility: Optional[Dict]
    selected_laptop: Optional[str]
    ticket_created: Optional[bool]
    current_step: str
    user_wants_to_proceed: Optional[bool]
    conversation_history: List[Dict]  # Track conversation for context


# Node functions
def collect_employee_id(state: AgentState) -> AgentState:
    """Node 1: Collect and validate employee ID using LlamaStack responses API."""
    logger.info(
        f"collect_employee_id called - current_step: {state.get('current_step')}"
    )
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    logger.debug(f"Last message: {last_message}")
    logger.debug(f"Messages count: {len(messages)}")

    if not last_message or not isinstance(last_message, HumanMessage):
        # Initial prompt - only generate if we don't have any messages yet
        if not messages:
            prompt = "You are a helpful laptop refresh assistant. Please introduce yourself and ask the user for their 4-digit employee ID to help with their laptop refresh request."
            messages_to_send = [{"role": "system", "content": prompt}]

            response = laptop_refresh_agent.create_response_with_retry(messages_to_send)
            state["messages"].append(AIMessage(content=response))

        # Set state to wait for user input
        state["current_step"] = "waiting_for_employee_id"
        return state

    # Extract employee ID from user message
    user_input = last_message.content.strip()

    # Simple validation - look for 4-digit number
    import re

    employee_id_match = re.search(r"\b\d{4}\b", user_input)

    if employee_id_match:
        employee_id = employee_id_match.group()
        state["employee_id"] = employee_id

        # Use LlamaStack responses API to get employee information
        prompt = f"Look up the laptop information for employee ID {employee_id}. If not found, simply say 'Employee ID {employee_id} was not found in the database.'"
        messages_to_send = [{"role": "system", "content": prompt}]

        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

        # Check if we got valid employee info
        if (
            "wasn't able to find" in response.lower()
            or "unavailable" in response.lower()
            or "not found" in response.lower()
        ):
            # Ask for a new employee ID instead of showing the lookup response
            error_msg = f"I'm sorry, employee ID {employee_id} was not found in our database. Could you please provide your correct 4-digit employee ID?"
            state["messages"].append(AIMessage(content=error_msg))
            state["current_step"] = (
                "waiting_for_employee_id"  # Stay in ID collection mode
            )
            return state

        # Store the response which should contain employee info
        state["employee_info"] = {"response": response}

        # Add the employee lookup response to the conversation
        state["messages"].append(AIMessage(content=response))

        # Move to next step
        state["current_step"] = "checking_eligibility"
        return state
    else:
        prompt = f"The user provided '{user_input}' but you need a 4-digit employee ID. Ask them again for their 4-digit employee ID."
        messages_to_send = [{"role": "system", "content": prompt}]

        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)
        state["messages"].append(AIMessage(content=response))
        return state


def check_eligibility(state: AgentState) -> AgentState:
    """Node 2: Check laptop eligibility and provide summary using LlamaStack responses API."""
    employee_info = state["employee_info"]
    if not employee_info:
        response = "I don't have your employee information. Please provide your 4-digit employee ID first."
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "collecting_employee_id"
        return state

    # Use LlamaStack responses API to check eligibility following the prompt requirements
    prompt = f"""
    You have the employee information for employee ID {state['employee_id']}: {state["employee_info"]}

    Search the knowledge base for the company's laptop refresh policy and determine if this employee is eligible for a laptop replacement. Specifically:

    1. Look up the corporate laptop refresh policy to find the refresh cycle/interval
    2. Compare the users current laptop age against the policy requirements
    3. Provide a clear summary to the user including their laptop details and eligibility status. The summary should speak directly to the user.
    4. CRITICAL: If they ARE eligible for a replacement, ask if they'd like to proceed to review laptop options
    5. CRITICAL: If they are NOT eligible, DO NOT ask about laptop options. Instead, inform them of the policy, when they would become eligible, and offer to help with other questions about the policy

    Present this information conversationally to the user, including their current laptop details (name, employee ID, location, purchase date, laptop age, model, serial number) and whether they can request a replacement today.
    """

    messages_to_send = [{"role": "user", "content": prompt}]
    response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

    # Store the eligibility response
    state["laptop_eligibility"] = {"response": response}
    state["messages"].append(AIMessage(content=response))

    # Check if user is eligible - look for clear eligibility indicators
    response_lower = response.lower()

    # First check for explicit eligibility indicators
    eligible_phrases = [
        "you are eligible",
        "eligible for a replacement",
        "would you like to proceed",
        "proceed to review laptop options",
    ]
    is_eligible = any(phrase in response_lower for phrase in eligible_phrases)

    # Then check for non-eligibility indicators
    ineligible_phrases = [
        "not eligible",
        "not yet eligible",
        "not currently eligible",
        "would likely be rejected",
        "does not meet",
        "you are not",
        "ineligible",
        "will become eligible",
        "not old enough",
    ]
    is_ineligible = any(phrase in response_lower for phrase in ineligible_phrases)

    # Route based on eligibility status
    if is_eligible and not is_ineligible:
        state["current_step"] = "waiting_for_proceed_confirmation"
    else:
        # For ineligible users, check if the response incorrectly asks about proceeding
        if any(
            phrase in response_lower
            for phrase in [
                "would you like to proceed",
                "proceed to review",
                "review laptop options",
            ]
        ):
            # The LLM incorrectly asked about proceeding despite being ineligible
            # Add a clarification message and route to general input
            clarification = "I apologize for the confusion in my previous message. Since you are not currently eligible for a laptop replacement, I cannot show you laptop options at this time. If you have any other questions about the laptop refresh policy, please let me know."
            state["messages"].append(AIMessage(content=clarification))

        # Default to general input for unclear or ineligible cases
        state["current_step"] = "waiting_for_general_input"
    return state


def handle_general_input(state: AgentState) -> AgentState:
    """Handle general user input when not eligible or in a general conversation state."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if not last_message or not isinstance(last_message, HumanMessage):
        state["current_step"] = "waiting_for_general_input"
        return state

    user_input = last_message.content.strip()

    # Use LLM to analyze user intent
    intent_prompt = f"""
    Analyze the user's message and determine their intent. The user said: "{user_input}"

    Context: This user is NOT currently eligible for a laptop replacement under standard policy.

    Classify the user's intent as one of the following:
    1. FAREWELL - User wants to end the conversation (goodbye, bye, thanks, etc.)
    2. PROCEED_ANYWAY - User wants to see laptop options despite being ineligible (proceed, show options, I want to see, etc.)
    3. GENERAL_QUESTION - User has questions about policy or general assistance

    Respond with only the classification: FAREWELL, PROCEED_ANYWAY, or GENERAL_QUESTION
    """

    intent_messages = [{"role": "user", "content": intent_prompt}]
    intent_response = (
        laptop_refresh_agent.create_response_with_retry(intent_messages).strip().upper()
    )

    if "FAREWELL" in intent_response:
        response = "Thank you for using the laptop refresh service. Have a great day!"
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "end"
        return state
    elif "PROCEED_ANYWAY" in intent_response:
        # User wants to proceed despite being ineligible - allow but with warning
        response = "I understand you'd like to proceed. While you're not currently eligible under the standard policy, I can show you the available options. Please note that any request would need special approval and may be subject to additional justification requirements. Would you like to see the available laptop options?"
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "waiting_for_proceed_confirmation"
        return state
    else:  # GENERAL_QUESTION or unclear
        # For any other input, provide a helpful response
        prompt = f"The user said '{user_input}'. This user is NOT currently eligible for a laptop replacement under standard policy. Provide a helpful response about laptop refresh policies or general assistance. If they're asking about their eligibility again, remind them they are not currently eligible and when they will become eligible."
        messages_to_send = [{"role": "user", "content": prompt}]
        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "waiting_for_general_input"
        return state


def handle_proceed_confirmation(state: AgentState) -> AgentState:
    """Handle user's response to proceed with laptop selection."""
    logger.info(
        f"handle_proceed_confirmation called with current_step: {state.get('current_step')}"
    )
    logger.info(
        f"handle_proceed_confirmation: employee_info = {state.get('employee_info')}"
    )
    logger.info(
        f"handle_proceed_confirmation: employee_id = {state.get('employee_id')}"
    )
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if not last_message or not isinstance(last_message, HumanMessage):
        # No user input to process, stay in waiting state
        state["current_step"] = "waiting_for_proceed_confirmation"
        return state

    user_input = last_message.content.strip()
    logger.info(f"User input for proceed confirmation: '{user_input}'")

    # Use LLM to analyze user intent for proceed confirmation
    intent_prompt = f"""
    The user was asked if they want to proceed with reviewing laptop options. They responded: "{user_input}"

    Classify their response as one of the following:
    1. YES - User wants to proceed (yes, sure, okay, proceed, continue, etc.)
    2. NO - User does not want to proceed or wants to end conversation (no, cancel, stop, bye, etc.)
    3. UNCLEAR - Response is ambiguous or unclear

    Respond with only the classification: YES, NO, or UNCLEAR
    """

    intent_messages = [{"role": "user", "content": intent_prompt}]
    intent_response = (
        laptop_refresh_agent.create_response_with_retry(intent_messages).strip().upper()
    )

    if "YES" in intent_response:
        logger.info("User wants to proceed - setting current_step to selecting_laptop")
        logger.info(
            f"State before setting to selecting_laptop: employee_info = {state.get('employee_info')}"
        )
        state["user_wants_to_proceed"] = True
        state["current_step"] = "selecting_laptop"
        logger.info(
            f"State after setting to selecting_laptop: employee_info = {state.get('employee_info')}"
        )
        return state
    elif "NO" in intent_response:
        state["user_wants_to_proceed"] = False
        response = "No problem! If you change your mind or need help with anything else, feel free to ask."
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "end"
        return state
    else:  # UNCLEAR
        response = "Please let me know if you'd like to proceed with reviewing the available laptop options (yes/no)."
        state["messages"].append(AIMessage(content=response))
        return state


def select_laptop(state: AgentState) -> AgentState:
    """Node 3: Present laptop options using LlamaStack responses API."""
    logger.info(f"select_laptop called with current_step: {state.get('current_step')}")
    logger.info(f"select_laptop: full state keys = {list(state.keys())}")
    logger.info(f"select_laptop: employee_info = {state.get('employee_info')}")
    logger.info(f"select_laptop: employee_id = {state.get('employee_id')}")

    # Check eligibility status but allow ineligible users to proceed with warnings
    laptop_eligibility = state.get("laptop_eligibility", {})
    user_is_ineligible = False
    if laptop_eligibility:
        eligibility_response = laptop_eligibility.get("response", "").lower()
        if any(
            phrase in eligibility_response
            for phrase in [
                "not eligible",
                "not yet eligible",
                "not currently eligible",
                "you are not",
            ]
        ):
            user_is_ineligible = True
            logger.info("User is not eligible but proceeding anyway")

    employee_info = state["employee_info"]
    if not employee_info:
        logger.warning("No employee info found, redirecting to collect employee ID")
        response = "I don't have your employee information. Please start over."
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "collecting_employee_id"
        return state

    logger.info("Employee info found, proceeding to get laptop options")

    # Use LlamaStack responses API to get and present laptop options following prompt requirements
    if user_is_ineligible:
        prompt = """
        The user wants to see laptop options even though they are not currently eligible under standard policy. Search the laptop refresh knowledge base and present them with all available laptop models based on their location. CRITICAL Include detailed specifications for each option and ask them to choose one specific laptop.

        IMPORTANT: Include a warning that they are not currently eligible under standard policy and any request would require special approval and justification.

        Ask them to choose one specific laptop if they wish to proceed with a special request.

        Only use information from the knowledge base - don't add external details.
        """
    else:
        prompt = """
        The user wants to see their laptop options. Search the laptop refresh knowledge base and present them with all available laptop models based on their location. CRITICAL Include detailed specifications for each option and ask them to choose one specific laptop.

        Only use information from the knowledge base - don't add external details.
        """

    # Build conversation context for LlamaStack responses API
    messages_to_send = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            messages_to_send.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages_to_send.append({"role": "assistant", "content": msg.content})

    # Add the current prompt
    messages_to_send.append({"role": "system", "content": prompt})

    logger.info(
        f"Sending {len(messages_to_send)} messages to LlamaStack for laptop selection"
    )
    response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

    state["messages"].append(AIMessage(content=response))
    state["current_step"] = "waiting_for_laptop_selection"
    return state


def handle_laptop_selection(state: AgentState) -> AgentState:
    """Handle user's laptop selection using LlamaStack responses API."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if not last_message or not isinstance(last_message, HumanMessage):
        return state

    user_input = last_message.content.strip()

    # Use LlamaStack responses API to process the laptop selection
    prompt = f"""
    The user has made a laptop selection: "{user_input}"

    Please validate their selection against the list of available laptops you previously provided. If it's a valid selection:
    1. Confirm their selection
    2. Ask if they would like to proceed with the creation of a ServiceNow ticket for laptop refresh

    If it's not a valid selection, ask them to choose one of the available options from the list.

    CRITICAL: Do not create a service now ticket yet - only ask for confirmation.
    """

    # Build conversation context for LlamaStack responses API
    messages_to_send = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            messages_to_send.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages_to_send.append({"role": "assistant", "content": msg.content})

    # Add the current prompt
    messages_to_send.append({"role": "system", "content": prompt})

    response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

    # Use LLM to determine if the selection was valid and confirmed
    validation_prompt = f"""
    Based on the agent's response: "{response}"

    Did the agent confirm a valid laptop selection and ask about creating a ServiceNow ticket?

    Respond with only:
    VALID - If the agent confirmed a laptop selection and asked about ticket creation
    INVALID - If the agent said the selection was invalid or asked to choose again
    """

    validation_messages = [{"role": "user", "content": validation_prompt}]
    validation_response = (
        laptop_refresh_agent.create_response_with_retry(validation_messages)
        .strip()
        .upper()
    )

    if "VALID" in validation_response:
        state["selected_laptop"] = user_input  # Store the user's selection
        state["current_step"] = "waiting_for_ticket_confirmation"
    else:
        # Invalid selection - stay in laptop selection mode
        state["current_step"] = "waiting_for_laptop_selection"

    state["messages"].append(AIMessage(content=response))
    return state


def handle_ticket_confirmation(state: AgentState) -> AgentState:
    """Node 4: Handle ServiceNow ticket creation confirmation using LlamaStack responses API."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if not last_message or not isinstance(last_message, HumanMessage):
        return state

    user_input = last_message.content.strip()

    # Use LLM to analyze user intent for ticket creation
    intent_prompt = f"""
    The user was asked if they want to create a ServiceNow ticket for their laptop refresh request. They responded: "{user_input}"

    Classify their response as one of the following:
    1. YES - User wants to create the ticket (yes, proceed, create, sure, okay, etc.)
    2. NO - User does not want to create the ticket (no, cancel, stop, etc.)
    3. UNCLEAR - Response is ambiguous or unclear

    Respond with only the classification: YES, NO, or UNCLEAR
    """

    intent_messages = [{"role": "user", "content": intent_prompt}]
    intent_response = (
        laptop_refresh_agent.create_response_with_retry(intent_messages).strip().upper()
    )

    if "YES" in intent_response:
        # Use LlamaStack responses API to create the ticket
        employee_id = state["employee_id"]
        selected_laptop = state["selected_laptop"]

        prompt = f"""
        Create a ServiceNow ticket for the user's laptop refresh request. Use employee ID {employee_id} and their selected laptop model {selected_laptop}. CRITICAL after creating the ticket, tell the user their ticket number. Output: Your service now ticket number is XXXX
        """

        messages_to_send = [{"role": "system", "content": prompt}]
        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

        state["ticket_created"] = True
        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "end"
    elif "NO" in intent_response:
        prompt = "Acknowledge that the user doesn't want to create a ticket and offer to help with anything else."
        messages_to_send = [{"role": "system", "content": prompt}]
        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

        state["messages"].append(AIMessage(content=response))
        state["current_step"] = "end"
    else:  # UNCLEAR
        prompt = f"The user said '{user_input}' when asked about creating a ticket. Ask them to clarify: do they want to create the ServiceNow ticket? (yes/no)"
        messages_to_send = [{"role": "system", "content": prompt}]
        response = laptop_refresh_agent.create_response_with_retry(messages_to_send)

        state["messages"].append(AIMessage(content=response))

    return state


# Routing function
def route_next_step(state: AgentState) -> str:
    """Route to the next step based on current state."""
    current_step = state.get("current_step", "collecting_employee_id")

    routing_map = {
        "collecting_employee_id": "collect_employee_id",
        "waiting_for_employee_id": END,  # Wait for user input
        "checking_eligibility": "check_eligibility",
        "waiting_for_general_input": END,  # Wait for user input (not eligible)
        "handle_general_input": "handle_general_input",  # Handle general conversation
        "waiting_for_proceed_confirmation": END,  # Wait for user input
        "handle_proceed_confirmation": "handle_proceed_confirmation",  # Handle user's proceed confirmation
        "selecting_laptop": "select_laptop",
        "waiting_for_laptop_selection": END,  # Wait for user input
        "handle_laptop_selection": "handle_laptop_selection",  # Handle user's laptop selection
        "waiting_for_ticket_confirmation": END,  # Wait for user input
        "handle_ticket_confirmation": "handle_ticket_confirmation",  # Handle user's ticket confirmation
        "end": END,
    }

    next_step = routing_map.get(current_step, "collect_employee_id")
    logger.info(
        f"route_next_step: current_step='{current_step}' -> next_step='{next_step}'"
    )
    return next_step


# Dispatcher node that routes to the correct handler
def dispatcher(state: AgentState) -> AgentState:
    """Dispatcher node that routes to the correct handler based on current_step."""
    current_step = state.get("current_step", "collecting_employee_id")
    logger.info(f"Dispatcher called with current_step: {current_step}")

    if current_step == "collecting_employee_id":
        return collect_employee_id(state)
    elif current_step == "checking_eligibility":
        return check_eligibility(state)
    elif current_step == "handle_general_input":
        return handle_general_input(state)
    elif current_step == "handle_proceed_confirmation":
        return handle_proceed_confirmation(state)
    elif current_step == "selecting_laptop":
        return select_laptop(state)
    elif current_step == "handle_laptop_selection":
        return handle_laptop_selection(state)
    elif current_step == "handle_ticket_confirmation":
        return handle_ticket_confirmation(state)
    else:
        logger.warning(f"Unknown current_step: {current_step}")
        return state


# Create the graph
def create_laptop_refresh_graph() -> StateGraph:
    """Create and configure the LangGraph for laptop refresh workflow."""

    # Create the graph
    workflow = StateGraph(AgentState)

    # Add single dispatcher node
    workflow.add_node("dispatcher", dispatcher)

    # Set entry point
    workflow.set_entry_point("dispatcher")

    # Add conditional routing from dispatcher
    workflow.add_conditional_edges(
        "dispatcher",
        route_next_step,
        {
            "collect_employee_id": "dispatcher",
            "check_eligibility": "dispatcher",
            "handle_general_input": "dispatcher",
            "handle_proceed_confirmation": "dispatcher",
            "select_laptop": "dispatcher",
            "handle_laptop_selection": "dispatcher",
            "handle_ticket_confirmation": "dispatcher",
            "waiting_for_employee_id": END,
            "waiting_for_general_input": END,
            "waiting_for_proceed_confirmation": END,
            "waiting_for_laptop_selection": END,
            "waiting_for_ticket_confirmation": END,
            "end": END,
            END: END,
        },
    )

    return workflow.compile(debug=False)


def main():
    """Main function to run the LangGraph laptop refresh agent."""
    print("=== LangGraph Laptop Refresh Agent ===")
    print("This agent uses LlamaStack to help with laptop refresh requests")
    print("Type 'quit' to exit")
    print("-" * 50)

    # No agent initialization needed - using responses API directly

    # Create the graph
    app = create_laptop_refresh_graph()

    # Initial state
    initial_state = {
        "messages": [],
        "employee_id": None,
        "employee_info": None,
        "laptop_eligibility": None,
        "selected_laptop": None,
        "ticket_created": False,
        "current_step": "collecting_employee_id",
        "user_wants_to_proceed": None,
        "conversation_history": [],
    }

    # Run the initial step
    try:
        logger.info("Starting initial invocation of the graph")
        result = app.invoke(initial_state)
        logger.info(
            f"Initial invocation completed, result state: {result.get('current_step')}"
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

                    # Reset current_step to continue processing based on current state
                    current_step = result.get("current_step")
                    if current_step == "waiting_for_employee_id":
                        result["current_step"] = "collecting_employee_id"
                    elif current_step == "waiting_for_general_input":
                        result["current_step"] = "handle_general_input"
                    elif current_step == "waiting_for_proceed_confirmation":
                        result["current_step"] = "handle_proceed_confirmation"
                    elif current_step == "waiting_for_laptop_selection":
                        result["current_step"] = "handle_laptop_selection"
                    elif current_step == "waiting_for_ticket_confirmation":
                        result["current_step"] = "handle_ticket_confirmation"

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
                    if result.get("current_step") == "end":
                        print("\n" + "=" * 50)
                        print("Laptop refresh process completed!")
                        print("Starting new conversation...")
                        print("=" * 50)

                        # Reset state for next conversation without generating welcome message
                        result = {
                            "messages": [],
                            "employee_id": None,
                            "employee_info": None,
                            "laptop_eligibility": None,
                            "selected_laptop": None,
                            "ticket_created": False,
                            "current_step": "waiting_for_employee_id",  # Start in waiting state
                            "user_wants_to_proceed": None,
                            "conversation_history": [],
                        }

            except KeyboardInterrupt:
                break

    except Exception as e:
        print(f"Error running agent: {e}")

    print("\nGoodbye!")


if __name__ == "__main__":
    main()
