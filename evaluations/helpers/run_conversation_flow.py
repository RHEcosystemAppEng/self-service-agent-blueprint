#!/usr/bin/env python3

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .openshift_chat_client import OpenShiftChatClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationFlowTester:
    """Test runner for conversation flows"""

    def __init__(
        self,
        test_script: str = "chat-responses-request-mgr.py",
        reset_conversation: bool = False,
        initial_message: Optional[str] = None,
        skip_initial_message: bool = False,
        message_timeout: int = 60,
    ) -> None:
        """
        Initialize the ConversationFlowTester.

        Args:
            test_script: Name of the test script to execute (default: "chat-responses-request-mgr.py")
            reset_conversation: If True, send 'reset' message at the start of each conversation
            initial_message: Message to send after reset instead of the default introduction prompt.
                             Only used when reset_conversation is True.
            skip_initial_message: If True, skip sending any initial message after reset, allowing
                                  the first question to serve as the opening message.
            message_timeout: Timeout in seconds for individual message send/response operations (default: 60)
        """
        self.test_script = test_script
        self.reset_conversation = reset_conversation
        self.initial_message = initial_message
        self.skip_initial_message = skip_initial_message
        self.message_timeout = message_timeout
        self.conversation_history: list[Any] = []
        self.total_app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}

    def run_flow(
        self,
        questions: list[str],
        authoritative_user_id: str,
        initial_message: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Run a conversation flow with the given questions.

        Starts a session with the agent, sends each question in sequence,
        and collects the responses. Returns the complete conversation.

        Args:
            questions: List of questions/messages to send to the agent
            authoritative_user_id: The authoritative user ID for this conversation

        Returns:
            List of conversation turns with role and content for each message

        Raises:
            Exception: If there are issues with the OpenShift session or communication
        """
        conversation = []

        # Create a new client for this flow with the specific authoritative_user_id
        client = OpenShiftChatClient(
            authoritative_user_id,
            test_script=self.test_script,
            reset_conversation=self.reset_conversation,
            initial_message=initial_message or self.initial_message,
            skip_initial_message=self.skip_initial_message,
            message_timeout=self.message_timeout,
        )

        try:
            client.start_session()

            # First, get the agent initialization message
            agent_init = client.get_agent_initialization()
            # If an initial message was sent, record it as the first user turn
            effective_initial = initial_message or self.initial_message
            if effective_initial and self.reset_conversation:
                conversation.append({"role": "user", "content": effective_initial})
            # Only record agent_init if it's non-empty (skip_initial_message returns "")
            if agent_init:
                conversation.append({"role": "assistant", "content": agent_init})

            # Then process user questions
            for i, question in enumerate(questions):
                response = client.send_message(question)

                # Add user message
                conversation.append({"role": "user", "content": question})
                # Add assistant response
                conversation.append({"role": "assistant", "content": response})

                # Keep the old format for conversation_history if needed
                self.conversation_history.append({"role": "user", "content": question})
                self.conversation_history.append(
                    {"role": "assistant", "content": response}
                )

        finally:
            # Request token summary before closing (if supported by deployed version)
            try:
                if client.session_active:
                    logger.debug("Attempting to request token summary from agent...")
                    # This will work when chat-lg-state.py includes the **tokens** command
                    token_response = client.send_message("**tokens**")
                    logger.debug(f"Token request response: {token_response}")
            except Exception as e:
                logger.debug(f"Token request not supported by current deployment: {e}")

            client.close_session()

            # Collect app tokens from this conversation
            app_tokens = client.get_app_tokens()
            logger.info(f"App tokens from conversation: {app_tokens}")
            logger.info(
                f"Session captured {len(client.session_output)} lines of output"
            )

            self.total_app_tokens["input"] += app_tokens["input"]
            self.total_app_tokens["output"] += app_tokens["output"]
            self.total_app_tokens["total"] += app_tokens["total"]
            self.total_app_tokens["calls"] += app_tokens["calls"]

            logger.info(f"Total app tokens so far: {self.total_app_tokens}")

        return conversation

    def run_flows(
        self,
        input_dir: str = "conversations_config/conversations",
        output_dir: str = "results/conversation_results",
    ) -> None:
        """
        Process all conversation files in the input directory and run them through run_flow.

        Reads all JSON files from the input directory, extracts user questions
        from each conversation, runs the flow with those questions, and saves
        the results to the output directory.

        Args:
            input_dir: Directory containing conversation JSON files to process
            output_dir: Directory where results will be saved

        Raises:
            json.JSONDecodeError: If a conversation file contains invalid JSON
            Exception: If there are issues processing conversations or saving results
        """

        # Create directories if they don't exist
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Get all JSON files from the input directory
        if not os.path.exists(input_dir):
            logger.warning(f"Input directory {input_dir} does not exist")
            return

        json_files = [f for f in os.listdir(input_dir) if f.endswith(".json")]

        if not json_files:
            logger.info(f"No JSON files found in {input_dir}")
            return

        logger.info(f"Found {len(json_files)} JSON files to process")

        for filename in json_files:
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)

            try:
                # Load the conversation from JSON
                with open(input_path, "r", encoding="utf-8") as f:
                    conversation_data = json.load(f)

                # Expected format: object with metadata and conversation
                if not isinstance(conversation_data, dict):
                    logger.error(
                        f"Invalid conversation format in {filename} - expected object with metadata"
                    )
                    continue

                metadata = conversation_data.get("metadata", {})
                authoritative_user_id = metadata.get("authoritative_user_id")
                turns = conversation_data.get("conversation", [])

                if not authoritative_user_id:
                    logger.error(
                        f"No authoritative_user_id found in metadata for {filename}"
                    )
                    continue

                # Extract questions from the conversation turns
                questions = []
                for turn in turns:
                    if isinstance(turn, dict) and turn.get("role") == "user":
                        questions.append(turn.get("content", ""))

                if not questions:
                    logger.warning(f"No user questions found in {filename}")
                    continue

                # Optionally use the first user message as the post-reset initial message
                initial_message = None
                if (
                    metadata.get("use_first_message_as_initial")
                    and self.reset_conversation
                ):
                    initial_message = questions[0]
                    questions = questions[1:]
                    logger.info(
                        f"Using first message as initial: {initial_message[:100]}"
                    )

                logger.info(
                    f"Processing {filename} with {len(questions)} questions using authoritative_user_id: {authoritative_user_id}"
                )

                # Run the flow with extracted questions and authoritative_user_id
                results = self.run_flow(
                    questions, authoritative_user_id, initial_message=initial_message
                )

                # Format results in the new conversation format with metadata
                formatted_results = {
                    "metadata": {
                        "authoritative_user_id": authoritative_user_id,
                        "description": f"Test results from {filename}",
                    },
                    "conversation": results,
                }

                # Save results to output directory
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(formatted_results, f, indent=2, ensure_ascii=False)

                logger.info(f"Results saved to {output_path}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON in {filename}: {e}")
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")

        logger.info("Flows processing completed")

        # Print token usage summary using shared function
        from .token_counter import print_token_summary

        print_token_summary(
            app_tokens=self.total_app_tokens, save_file_prefix="run_conversations"
        )
