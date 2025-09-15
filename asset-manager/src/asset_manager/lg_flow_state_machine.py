#!/usr/bin/env python3
"""
LangGraph-based state machine and agent session management.

This module contains the StateMachine and AgentSession classes for managing
conversational flows using LangGraph with persistent checkpoint storage.
"""
import logging
from pathlib import Path
from typing import Annotated, Dict, List, Optional, TypedDict

import yaml
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# Import SqliteSaver - assume it's available with minimal fallback for development
try:
    from langgraph_checkpoint_sqlite import SqliteSaver
except ImportError:
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        # Minimal fallback for development environments
        SqliteSaver = None

logger = logging.getLogger(__name__)


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


class StateMachine:
    """Configurable state machine engine for conversation flows."""

    def __init__(self, config_path: str):
        """Initialize the state machine with configuration from YAML file."""
        self.config_path = Path(config_path)
        self.config = self._load_config()

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

            # Add conversation_history placeholder
            conversation_history = ""
            for i, msg in enumerate(messages):
                if hasattr(msg, "content"):
                    msg_type = getattr(msg, "__class__", None).__name__
                    if msg_type == "HumanMessage":
                        conversation_history += f"User: {msg.content}\n"
                    elif msg_type == "AIMessage":
                        conversation_history += f"Assistant: {msg.content}\n"
            format_data["conversation_history"] = conversation_history.strip()

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

    def process_llm_processor_state(
        self, state: dict, state_config: dict, agent
    ) -> dict:
        """Process llm_processor type states - completely generic and configuration-driven."""

        # Step 1: Determine the prompt to use
        prompt = self._get_prompt_for_state(state, state_config)

        # Step 2: Prepare messages and send to LLM with retry logic for empty responses
        # Check if state config wants to use conversation history
        use_conversation_history = state_config.get("use_conversation_history", False)

        if use_conversation_history:
            # Convert state messages to API format and add current prompt as system message
            messages_to_send = []

            # Add the prompt as a system message
            messages_to_send.append({"role": "system", "content": prompt})

            # Add conversation history
            state_messages = state.get("messages", [])
            logger.info(
                f"Using conversation history with {len(state_messages)} messages"
            )
            for msg in state_messages:
                if hasattr(msg, "content"):
                    msg_type = getattr(msg, "__class__", None).__name__
                    if msg_type == "HumanMessage":
                        messages_to_send.append(
                            {"role": "user", "content": msg.content}
                        )
                    elif msg_type == "AIMessage":
                        messages_to_send.append(
                            {"role": "assistant", "content": msg.content}
                        )

            logger.info(
                f"Sending {len(messages_to_send)} messages to LLM (1 system + {len(messages_to_send) - 1} conversation)"
            )
        else:
            # Traditional approach - send prompt as single user message
            messages_to_send = [{"role": "user", "content": prompt}]
            logger.info(
                "Using traditional approach - sending prompt as single user message"
            )

        temperature = state_config.get(
            "temperature"
        )  # Get temperature from state config
        response = agent.create_response_with_retry(
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

    def process_intent_classifier_state(
        self, state: dict, state_config: dict, agent
    ) -> dict:
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
            agent.create_response_with_retry(
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
                    response = agent.create_response_with_retry(
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

    def process_llm_validator_state(
        self, state: dict, state_config: dict, agent
    ) -> dict:
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
        response = agent.create_response_with_retry(
            messages_to_send, self._get_retry_count(), temperature=temperature
        )

        # Use LLM to determine if validation passed
        success_validation_prompt = self._format_text(
            state_config.get("success_validation_prompt", ""),
            {"llm_response": response},
        )
        validation_messages = [{"role": "user", "content": success_validation_prompt}]
        validation_response = (
            agent.create_response_with_retry(
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

    def process_state(self, state: dict, agent) -> dict:
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
            return self.process_llm_processor_state(state, state_config, agent)
        elif state_type == "intent_classifier":
            return self.process_intent_classifier_state(state, state_config, agent)
        elif state_type == "llm_validator":
            return self.process_llm_validator_state(state, state_config, agent)
        elif state_type == "terminal":
            return self.process_terminal_state(state, state_config)
        else:
            logger.error(f"Unknown state type: {state_type}")
            state["current_state"] = "end"
            return state


class ConversationSession:
    """
    Encapsulates the state machine, graph, and persistent conversation state for a single conversation session.
    Uses LangGraph checkpoints and threads for persistence across process restarts.
    """

    def __init__(
        self,
        agent,
        thread_id: str = None,
        checkpoint_db_path: str = None,
    ):
        """
        Initialize a new conversation session with persistent checkpoint storage.

        Args:
            agent: Agent instance to use for this session (config includes state machine path)
            thread_id: Thread identifier for conversation persistence (defaults to generated ID)
            checkpoint_db_path: Path to SQLite checkpoint database (defaults to memory)
        """
        import uuid

        self.thread_id = thread_id or str(uuid.uuid4())
        self.agent = agent

        # Get state machine config path from agent configuration
        lg_config_path = agent.config.get(
            "lg_state_machine_config", "config/lg-prompts/chat-lg-state.yaml"
        )

        # Convert to absolute path relative to this script's location
        if not Path(lg_config_path).is_absolute():
            # Path relative to asset-manager root (parent of src/asset_manager)
            asset_manager_root = Path(__file__).parent.parent.parent
            self.config_path = asset_manager_root / lg_config_path
        else:
            self.config_path = Path(lg_config_path)

        # Initialize checkpoint storage with SqliteSaver
        self.checkpointer_cm = SqliteSaver.from_conn_string(str(checkpoint_db_path))
        self.checkpointer = self.checkpointer_cm.__enter__()

        # Initialize state machine
        self.state_machine = StateMachine(self.config_path)

        # Create the graph with checkpointer
        self.app = self._create_graph()

        # Thread configuration for this session
        self.thread_config = {"configurable": {"thread_id": self.thread_id}}

    def _create_graph(self):
        """Create the LangGraph workflow for this session with checkpoint persistence."""
        # Use the dynamic AgentState from the state machine
        workflow = StateGraph(self.state_machine.AgentState)

        # Add single dispatcher node
        workflow.add_node("dispatcher", self._dispatcher)

        # Set entry point
        workflow.set_entry_point("dispatcher")

        # Add conditional routing from dispatcher
        workflow.add_conditional_edges(
            "dispatcher",
            self._route_next_step,
            {
                "dispatcher": "dispatcher",
                END: END,
            },
        )

        # Compile with checkpointer for persistence
        return workflow.compile(checkpointer=self.checkpointer, debug=False)

    def _dispatcher(self, state: dict) -> dict:
        """Dispatcher that processes states using this session's state machine."""
        logger.info(
            f"Thread {self.thread_id} dispatcher called with current_state: {state.get('current_state')}"
        )

        # Use session agent
        return self.state_machine.process_state(state, self.agent)

    def _route_next_step(self, state: dict) -> str:
        """Route to the next step based on current state."""
        settings = self.state_machine.config.get("settings", {})
        current_state = state.get(
            "current_state", settings.get("initial_state", "collect_employee_id")
        )

        # Terminal state
        if self.state_machine.is_terminal_state(current_state):
            return END

        # Waiting states end (wait for user input)
        if self.state_machine.is_waiting_state(current_state):
            return END

        # All other states continue to dispatcher
        return "dispatcher"

    def get_initial_response(self) -> str:
        """Get the initial response from the agent by checking conversation history."""
        try:
            # Check if there's existing conversation state
            current_state = self.app.get_state(self.thread_config)

            if current_state.values and current_state.values.get("messages"):
                return ""
            else:
                # New conversation - initialize and get first response
                initial_state = self.state_machine.create_initial_state()
                result = self.app.invoke(initial_state, config=self.thread_config)

                if result.get("messages"):
                    last_message = result["messages"][-1]
                    if isinstance(last_message, AIMessage):
                        return last_message.content
                return ""
        except Exception as e:
            logger.error(
                f"Error getting initial response for thread {self.thread_id}: {e}"
            )
            return ""

    def send_message(self, message: str) -> str:
        """
        Send a message to the agent and return the response.
        Uses checkpointed thread state for persistence across process restarts.

        Args:
            message: The user message to send to the agent

        Returns:
            The agent's response message as a string
        """

        # Handle special commands
        if message.lower() in ["quit", "exit", "q"]:
            return "Session ended."

        if message.lower() == "**tokens**":
            try:
                # Try to import token stats, but handle gracefully if not available
                try:
                    from asset_manager.token_counter import get_token_stats

                    stats = get_token_stats()
                    return f"CURRENT_TOKEN_SUMMARY:INPUT:{stats.total_input_tokens}:OUTPUT:{stats.total_output_tokens}:TOTAL:{stats.total_tokens}:CALLS:{stats.call_count}:MAX_SINGLE_INPUT:{stats.max_input_tokens}:MAX_SINGLE_OUTPUT:{stats.max_output_tokens}:MAX_SINGLE_TOTAL:{stats.max_total_tokens}"
                except ImportError:
                    return "Token stats not available"
            except Exception:
                return "Token stats not available"

        if not message.strip():
            return "Please provide a valid message."

        try:
            # Get current thread state
            current_state = self.app.get_state(self.thread_config)

            # Initialize conversation if needed
            if not current_state.values:
                # First message - initialize with empty state and let the graph handle initialization
                initial_state = self.state_machine.create_initial_state()
                # Add the user message to initial state
                initial_state["messages"].append(HumanMessage(content=message))
                result = self.app.invoke(initial_state, config=self.thread_config)
            else:
                # Existing conversation - add user message and continue
                # Create input with just the new user message
                user_input = {"messages": [HumanMessage(content=message)]}

                # Get current state values
                current_values = current_state.values
                current_state_name = current_values.get("current_state")

                # Handle waiting states
                if self.state_machine.is_waiting_state(current_state_name):
                    states_config = self.state_machine.config.get("states", {})
                    if current_state_name in states_config:
                        state_config = states_config[current_state_name]
                        transitions = state_config.get("transitions", {})
                        next_state = transitions.get("user_input", current_state_name)
                        user_input["current_state"] = next_state

                # Invoke with the new message
                result = self.app.invoke(user_input, config=self.thread_config)

            # Extract agent response
            agent_response = ""
            if result and result.get("messages"):
                # Find the last AI message
                for msg in reversed(result["messages"]):
                    if isinstance(msg, AIMessage):
                        agent_response = msg.content
                        break

            # Check if conversation ended and reset if needed
            if result and self.state_machine.is_terminal_state(
                result.get("current_state")
            ):
                # Reset the thread for a new conversation
                reset_state = self.state_machine.reset_state_for_new_conversation()
                self.app.update_state(self.thread_config, reset_state)
                if agent_response:
                    agent_response += (
                        "\n\n[Conversation completed! Starting new conversation...]"
                    )
                else:
                    agent_response = (
                        "Conversation completed! Starting new conversation..."
                    )

            return (
                agent_response if agent_response else "No response received from agent"
            )

        except Exception as e:
            logger.error(f"Error processing message for thread {self.thread_id}: {e}")
            return f"Error processing message: {e}"

    def close(self):
        """Clean up resources, especially the SQLite context manager."""
        if hasattr(self, "checkpointer_cm") and self.checkpointer_cm is not None:
            try:
                self.checkpointer_cm.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing checkpointer context manager: {e}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.close()
