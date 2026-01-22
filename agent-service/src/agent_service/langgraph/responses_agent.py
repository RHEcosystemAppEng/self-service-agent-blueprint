import os
from typing import Any, Dict, Optional

import yaml
from agent_service.utils import create_llamastack_client
from opentelemetry.propagate import inject
from shared_models import configure_logging
from tracing_config.auto_tracing import tracingIsActive

from .util import load_config_from_path, resolve_agent_service_path

logger = configure_logging("agent-service")


class Agent:
    """
    Agent that loads configuration from agent YAML files and provides LlamaStack integration.
    """

    def __init__(
        self,
        agent_name: str,
        config: dict[str, Any],
        global_config: dict[str, Any] | None = None,
        system_message: str | None = None,
    ):
        """Initialize agent with provided configuration."""
        self.agent_name = agent_name
        self.config = config
        self.global_config = global_config or {}

        # Initialize LlamaStack client once for this agent
        # This client provides both native APIs and OpenAI-compatible APIs
        timeout = self.global_config.get("timeout", 120.0)
        self.llama_client = create_llamastack_client(timeout=timeout)

        self.model = self._get_model_for_agent()
        self.default_response_config = self._get_response_config()
        self.system_message = system_message or self._get_default_system_message()

        # Build tools once during initialization (without authoritative_user_id)
        mcp_server_configs = self.config.get("mcp_servers", [])
        self.tools = self._get_mcp_tools_to_use(mcp_server_configs)

        # Load shield configuration for input/output moderation
        # Check if SAFETY environment variables are configured
        safety_model = os.getenv("SAFETY")
        safety_url = os.getenv("SAFETY_URL")
        shields_available = bool(safety_model and safety_url)

        if shields_available:
            self.input_shields = self.config.get("input_shields", [])
            self.output_shields = self.config.get("output_shields", [])
        else:
            # Disable shields if SAFETY environment not configured
            self.input_shields = []
            self.output_shields = []
            if self.config.get("input_shields") or self.config.get("output_shields"):
                logger.warning(
                    "Shields configured in agent but SAFETY/SAFETY_URL environment variables not set. Shields will be disabled.",
                    agent_name=agent_name,
                )

        # Load categories to ignore (for handling false positives)
        self.ignored_input_categories = set(
            self.config.get("ignored_input_shield_categories", [])
        )
        self.ignored_output_categories = set(
            self.config.get("ignored_output_shield_categories", [])
        )

        logger.info(
            "Initialized Agent",
            agent_name=agent_name,
            model=self.model,
            tool_count=len(self.tools),
        )
        if self.input_shields:
            logger.info("Input shields configured", shields=self.input_shields)
            if self.ignored_input_categories:
                logger.info(
                    "Ignored input categories", categories=self.ignored_input_categories
                )
        if self.output_shields:
            logger.info("Output shields configured", shields=self.output_shields)
            if self.ignored_output_categories:
                logger.info(
                    "Ignored output categories",
                    categories=self.ignored_output_categories,
                )

    def _get_model_for_agent(self) -> str:
        """Get the model to use for the agent from configuration."""
        if self.config and self.config.get("model"):
            model = self.config["model"]
            logger.info("Using configured model", model=model)
            return str(model) if model is not None else ""

        try:
            models = self.llama_client.models.list()
            model_id = next(m.identifier for m in models if m.api_model_type == "llm")
            if model_id:
                logger.info("Using first available LLM model", model_id=model_id)
                return str(model_id)
        except Exception as e:
            logger.error(
                "Error getting models from LlamaStack",
                error=str(e),
                error_type=type(e).__name__,
            )

        raise RuntimeError(
            "Could not determine model from agent configuration or LlamaStack - no LLM models available"
        )

    def _get_response_config(self) -> dict[str, Any]:
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
            message = self.config["system_message"]
            return str(message) if message is not None else ""

        return ""

    def _get_vector_store_id(self, kb_name: str) -> str:
        """Get the vector store ID for a specific knowledge base."""
        try:
            # Use LlamaStack's OpenAI-compatible vector store API
            vector_stores = self.llama_client.vector_stores.list()
            matching_stores = []
            for vs in vector_stores.data:
                if vs.name and kb_name in vs.name:
                    matching_stores.append(vs)

            if matching_stores:
                latest_store = max(matching_stores, key=lambda x: x.created_at)
                logger.info(
                    "Found existing vector store",
                    vector_store_id=latest_store.id,
                    vector_store_name=latest_store.name,
                )
                return str(latest_store.id) if latest_store.id is not None else kb_name
            else:
                logger.warning(
                    "No vector store found for knowledge base, using fallback",
                    kb_name=kb_name,
                )
                return kb_name

        except Exception as e:
            logger.error(
                "Error finding vector store for knowledge base",
                kb_name=kb_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            return kb_name  # Return the kb_name as fallback

    def _get_mcp_tools_to_use(
        self,
        mcp_server_configs: list[dict[str, Any]] | None = None,
        authoritative_user_id: str | None = None,
        allowed_tools: list[str] | None = None,
    ) -> list[Any]:
        """Get complete tools array for LlamaStack responses API.

        Args:
            mcp_server_configs: List of MCP server configurations with name, uri, etc.
            authoritative_user_id: Optional user ID to pass to MCP servers
            allowed_tools: Optional list of tool names to restrict

        Returns:
            List of tool configurations for LlamaStack responses API
        """
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

        # Add MCP tools from server configurations
        if mcp_server_configs:
            for server_config in mcp_server_configs:
                try:
                    server_name = server_config.get("name")
                    server_uri = server_config.get("uri")

                    if not server_name or not server_uri:
                        logger.warning(
                            "Skipping MCP server with missing name or uri",
                            server_config=server_config,
                        )
                        continue

                    mcp_tool: Dict[str, Any] = {
                        "type": "mcp",
                        "server_label": server_name,
                        "server_url": server_uri,
                        "require_approval": server_config.get(
                            "require_approval", "never"
                        ),
                    }

                    # Build headers dictionary dynamically per request
                    tool_headers = {}

                    # Add headers if provided
                    if authoritative_user_id:
                        tool_headers["AUTHORITATIVE_USER_ID"] = authoritative_user_id

                    # Add tracing headers if tracing is active
                    if tracingIsActive():
                        # Inject current tracing context into headers
                        # This will add traceparent and tracestate headers
                        inject(tool_headers)
                        logger.debug(
                            "Injected tracing headers for MCP server",
                            server_name=server_name,
                            header_keys=list(tool_headers.keys()),
                        )

                    # Add ServiceNow API key header for pass-through authentication
                    # Read from environment dynamically, just like authoritative_user_id
                    snow_api_key = os.environ.get("SERVICENOW_API_KEY")
                    if snow_api_key:
                        tool_headers["SERVICE_NOW_TOKEN"] = snow_api_key

                    # Apply headers if any are present
                    if tool_headers:
                        mcp_tool["headers"] = tool_headers

                    # Add allowed_tools if specified (from parameter or config)
                    config_allowed_tools = server_config.get("allowed_tools")
                    if allowed_tools:
                        mcp_tool["allowed_tools"] = allowed_tools
                    elif config_allowed_tools:
                        mcp_tool["allowed_tools"] = config_allowed_tools

                    tools_to_use.append(mcp_tool)

                except Exception as e:
                    logger.error(
                        "Error building MCP tool for server config",
                        server_config=server_config,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

        logger.info("Built tools array", tool_count=len(tools_to_use))

        return tools_to_use

    def _run_moderation_shields(
        self,
        content: Any,
        shield_models: list[str],
        check_type: str = "input",
    ) -> tuple[bool, Optional[str]]:
        """
        Run moderation checks using OpenAI-compatible moderation API.

        Args:
            content: Either a string (for output) or list of message dicts (for input)
            shield_models: List of moderation model names (e.g., ["llama-guard-3"])
            check_type: "input" or "output" for logging purposes

        Returns:
            Tuple of (is_safe, error_message)
            - is_safe: True if content passes all shields
            - error_message: User-facing message if blocked, None if safe
        """
        if not shield_models or len(shield_models) == 0:
            return True, None

        # Use configured ignored categories from agent config based on check type
        if check_type == "input":
            ignored_categories = self.ignored_input_categories
        elif check_type == "output":
            ignored_categories = self.ignored_output_categories
        else:
            ignored_categories = set()

        # Prepare input for moderation API
        moderation_input: Any
        log_preview: str

        if isinstance(content, str):
            # Output shield: single string
            moderation_input = content
            log_preview = content[:100]
        elif isinstance(content, list):
            # Input shield: list of messages
            # Only check the last message (most recent user input)
            if len(content) == 0:
                return True, None

            last_msg = content[-1]
            if isinstance(last_msg, dict) and "content" in last_msg:
                moderation_input = str(last_msg["content"])
            elif isinstance(last_msg, str):
                moderation_input = last_msg
            else:
                logger.warning(
                    "Invalid last message format for moderation",
                    message_type=type(last_msg).__name__,
                )
                return True, None

            log_preview = f"last message, {len(moderation_input)} chars"
        else:
            logger.warning(
                "Invalid content type for moderation",
                content_type=type(content).__name__,
            )
            return True, None

        for shield_model in shield_models:
            try:
                logger.debug(
                    "Running shield on content",
                    check_type=check_type,
                    shield_model=shield_model,
                    preview=log_preview,
                )

                # Call OpenAI-compatible moderation API
                moderation_response = self.llama_client.moderations.create(
                    input=moderation_input, model=shield_model
                )

                # Check if content was flagged
                if moderation_response.results and len(moderation_response.results) > 0:
                    result = moderation_response.results[0]

                    if result.flagged:
                        # Check if any flagged categories are NOT in the ignored list
                        flagged_categories = {
                            cat
                            for cat, is_flagged in (result.categories or {}).items()
                            if is_flagged and cat not in ignored_categories
                        }

                        if flagged_categories:
                            # Log the violation with details including full content
                            logger.warning(
                                "Content flagged by shield",
                                check_type=check_type,
                                shield_model=shield_model,
                                categories=result.categories,
                                scores=result.category_scores,
                                content=repr(moderation_input),
                            )

                            # Return user-facing message
                            user_message = (
                                result.user_message
                                or "I apologize, but I cannot process that request due to safety concerns."
                            )
                            return False, user_message
                        else:
                            # Only ignored categories were flagged - allow content
                            logger.info(
                                "Content flagged by shield but only in ignored categories",
                                check_type=check_type,
                                shield_model=shield_model,
                                categories=result.categories,
                            )

            except Exception as e:
                logger.error(
                    "Error running shield",
                    check_type=check_type,
                    shield_model=shield_model,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Fail open - continue to next shield or allow if last shield
                continue

        # All shields passed
        return True, None

    def create_response_with_retry(
        self,
        messages: list[Any],
        max_retries: int = 3,
        temperature: float | None = None,
        additional_system_messages: list[str] | None = None,
        authoritative_user_id: str | None = None,
        allowed_tools: list[str] | None = None,
        skip_all_tools: bool = False,
        skip_mcp_servers_only: bool = False,
        current_state_name: str | None = None,
        token_context: str | None = None,
    ) -> tuple[str, bool]:
        """Create a response with retry logic for empty responses and errors."""
        default_response = "I apologize, but I'm having difficulty generating a response right now. Please try again."
        response = default_response
        last_error = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt plus retries
            try:
                response = self.create_response(
                    messages,
                    temperature=temperature,
                    additional_system_messages=additional_system_messages,
                    authoritative_user_id=authoritative_user_id,
                    allowed_tools=allowed_tools,
                    skip_all_tools=skip_all_tools,
                    skip_mcp_servers_only=skip_mcp_servers_only,
                    current_state_name=current_state_name,
                    token_context=token_context,
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
                        "Empty/error response, retrying",
                        attempt=attempt + 1,
                        max_attempts=max_retries + 1,
                        retry_delay=retry_delay,
                    )
                    import time

                    time.sleep(retry_delay)
                else:
                    logger.warning(
                        "All retry attempts failed",
                        max_attempts=max_retries + 1,
                        last_error=last_error or "Empty response",
                    )
                    response = "I apologize, but I'm having difficulty generating a response right now. Please try again."

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Exception on retry attempt",
                    attempt=attempt + 1,
                    max_retries=max_retries + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                if attempt >= max_retries:
                    response = "I apologize, but I'm experiencing technical difficulties. Please try again later."
                    break

        response_failed = response == default_response
        return response, response_failed

    def _check_response_errors(self, response: Any) -> str:
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
            logger.warning(
                "Error while checking response errors",
                error=str(e),
                error_type=type(e).__name__,
            )
            return f"Error checking failed: {e}"

    def _print_empty_response_debug_info(
        self,
        response: Any,
        current_state_name: Optional[str],
        skip_all_tools: bool,
        skip_mcp_servers_only: bool,
        tools_to_use: list[Any],
    ) -> None:
        """Print detailed debug information for empty responses.

        Only prints if SHOW_EMPTY_RESPONSE_INFO environment variable is set.
        """
        if not os.environ.get("SHOW_EMPTY_RESPONSE_INFO"):
            return

        print("=" * 80)
        print("EMPTY RESPONSE DETECTED - NO VALID CONTENT FOUND")
        print("=" * 80)
        if current_state_name:
            print(f"Current State (from YAML): {current_state_name}")
        print(f"Response ID: {getattr(response, 'id', 'N/A')}")
        print(f"Response status: {getattr(response, 'status', 'N/A')}")
        print(f"Response model: {getattr(response, 'model', 'N/A')}")
        print(f"Skip ALL tools: {skip_all_tools}")
        print(f"Skip MCP servers only: {skip_mcp_servers_only}")
        print(f"Tools count: {len(tools_to_use) if tools_to_use else 0}")
        print(
            f"Has output_text: {hasattr(response, 'output_text')}, value: '{getattr(response, 'output_text', 'N/A')}'"
        )
        if hasattr(response, "output") and response.output:
            print(f"Output array length: {len(response.output)}")
            for idx, item in enumerate(response.output):
                print(f"  Output[{idx}]: type={getattr(item, 'type', 'N/A')}")
                if hasattr(item, "content"):
                    print(
                        f"    content length: {len(item.content) if item.content else 0}"
                    )
                    if item.content:
                        for cidx, citem in enumerate(item.content):
                            print(
                                f"      content[{cidx}]: type={getattr(citem, 'type', 'N/A')}, text='{getattr(citem, 'text', 'N/A')}'"
                            )
        if hasattr(response, "text"):
            print(f"Response.text: {response.text}")
        print("=" * 80)

    def create_response(
        self,
        messages: list[Any],
        temperature: float | None = None,
        additional_system_messages: list[str] | None = None,
        authoritative_user_id: str | None = None,
        allowed_tools: list[str] | None = None,
        skip_all_tools: bool = False,
        skip_mcp_servers_only: bool = False,
        current_state_name: str | None = None,
        token_context: str | None = None,
    ) -> str:
        """Create a response using LlamaStack responses API.

        Args:
            messages: List of user/assistant messages
            temperature: Optional temperature override
            additional_system_messages: Optional list of additional system messages to include
            authoritative_user_id: Optional authoritative user ID to pass via X-LlamaStack-Provider-Data header to MCP servers
            allowed_tools: Optional list of tool names/types to restrict available tools (e.g., ['file_search'])
            skip_all_tools: If True, skip all tools (MCP servers and knowledge base)
            skip_mcp_servers_only: If True, skip only MCP servers (keep knowledge base tools)
            current_state_name: Optional name of the current state from the state machine YAML
        """
        try:
            # INPUT SHIELD: Check user input before processing
            if self.input_shields and messages and len(messages) > 0:
                # Check only the last message (most recent user input)
                is_safe, error_message = self._run_moderation_shields(
                    messages, self.input_shields, "input"
                )
                if not is_safe:
                    logger.info(
                        "Input blocked by shield",
                        agent_name=self.agent_name,
                        messages=repr(messages),
                    )
                    return (
                        error_message
                        or "I apologize, but I cannot process that request due to safety concerns."
                    )

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

            # Rebuild tools if any tool filtering is requested
            if skip_all_tools:
                # Skip all tools (no MCP servers, no knowledge base tools)
                tools_to_use = []
            elif skip_mcp_servers_only:
                # Skip MCP servers but keep knowledge base tools
                # Pass None/empty list for mcp_servers to exclude them
                tools_to_use = self._get_mcp_tools_to_use(
                    None, authoritative_user_id, allowed_tools
                )
            elif authoritative_user_id or allowed_tools:
                # Include MCP servers and knowledge base tools
                mcp_server_configs = self.config.get("mcp_servers", [])
                tools_to_use = self._get_mcp_tools_to_use(
                    mcp_server_configs, authoritative_user_id, allowed_tools
                )
            else:
                tools_to_use = self.tools

            # Use the existing LlamaStack client for response creation
            # Only pass tools if tools_to_use is not empty
            if tools_to_use:
                response = self.llama_client.responses.create(
                    input=messages_with_system,
                    model=self.model,
                    **response_config,
                    tools=tools_to_use,
                )
            else:
                response = self.llama_client.responses.create(
                    input=messages_with_system,
                    model=self.model,
                    **response_config,
                )

            # Import token counting if available
            try:
                from .token_counter import count_tokens_from_response

                # Use provided token context or fallback to default
                context = token_context or "chat_agent"

                count_tokens_from_response(
                    response, self.model, context, messages_with_system
                )
            except ImportError:
                pass  # Token counting is optional

            # Check for error conditions in the response
            error_info = self._check_response_errors(response)
            if error_info:
                logger.warning("Response error detected", error_info=error_info)
                return ""  # Return empty to trigger retry logic

            # Extract content from LlamaStack responses API format
            response_text = ""
            try:
                # Try output_text first (most common case)
                if (
                    hasattr(response, "output_text")
                    and response.output_text
                    and response.output_text.strip()
                ):
                    response_text = response.output_text

                # Try to find message in output array (handles MCP tool discovery responses)
                elif hasattr(response, "output") and response.output:
                    for output_item in response.output:
                        if (
                            hasattr(output_item, "type")
                            and output_item.type == "message"
                        ):
                            if hasattr(output_item, "content") and output_item.content:
                                for content_item in output_item.content:
                                    if hasattr(content_item, "text"):
                                        content = content_item.text
                                        if content and content.strip():
                                            response_text = content
                                            break
                            # Found message but it was empty, break to check fallbacks
                            break

                # Try other fallback fields
                if (
                    not response_text
                    and hasattr(response, "completion_message")
                    and hasattr(response.completion_message, "content")
                ):
                    content = response.completion_message.content
                    if isinstance(content, str) and content.strip():
                        response_text = content

                if not response_text and hasattr(response, "content"):
                    content = response.content
                    if isinstance(content, str) and content.strip():
                        response_text = content

                # No valid content found - print detailed debug info
                if not response_text:
                    self._print_empty_response_debug_info(
                        response,
                        current_state_name,
                        skip_all_tools,
                        skip_mcp_servers_only,
                        tools_to_use,
                    )
                    logger.warning("No valid content found in response")
                    return ""  # Return empty to trigger retry logic

            except Exception as e:
                logger.error(
                    "Error extracting content from response",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return f"Error processing response: {e}"

            # OUTPUT SHIELD: Check agent response before returning
            if self.output_shields and response_text:
                is_safe, error_message = self._run_moderation_shields(
                    response_text, self.output_shields, "output"
                )
                if not is_safe:
                    logger.info(
                        "Output blocked by shield",
                        agent_name=self.agent_name,
                        response_text=repr(response_text),
                    )
                    return (
                        error_message
                        or "I apologize, but I cannot provide that response due to safety concerns."
                    )

            return response_text

        except TimeoutError as e:
            logger.warning(
                "Timeout calling LlamaStack responses API",
                error=str(e),
                error_type=type(e).__name__,
            )
            return ""  # Return empty to trigger retry with longer timeout
        except ConnectionError as e:
            logger.warning(
                "Connection error calling LlamaStack responses API",
                error=str(e),
                error_type=type(e).__name__,
            )
            return ""  # Return empty to trigger retry
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "timeout" in error_msg
                or "connection" in error_msg
                or "network" in error_msg
            ):
                logger.warning(
                    "Network-related error calling LlamaStack",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return ""  # Return empty to trigger retry
            else:
                logger.error(
                    "Unexpected error calling LlamaStack responses API",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return (
                    f"Error: Unable to get response from LlamaStack responses API: {e}"
                )


class ResponsesAgentManager:
    """Manages multiple agent instances for the application."""

    def __init__(self) -> None:
        self.agents_dict = {}

        # Load the configuration using centralized path resolution
        try:
            config_path = resolve_agent_service_path("config")
            logger.info(
                "ResponsesAgentManager found config", config_path=str(config_path)
            )
        except FileNotFoundError as e:
            logger.error(
                "ResponsesAgentManager config not found",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        agent_configs = load_config_from_path(config_path)

        # Load global configuration (config.yaml)
        global_config_path = config_path / "config.yaml"
        global_config: Dict[str, Any] = {}
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

    def get_agent(self, agent_id: str) -> Any:
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

    def agents(self) -> dict[str, str]:
        """Return a dict mapping agent names to agent names (for compatibility with AgentManager)."""
        return {name: name for name in self.agents_dict.keys()}
