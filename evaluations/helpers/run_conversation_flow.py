#!/usr/bin/env python3

import datetime
import json
import logging
import os
from typing import Dict, List

from .openshift_chat_client import OpenShiftChatClient
from .token_counter import get_token_stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationFlowTester:
    """Test runner for conversation flows"""

    def __init__(self, test_script: str = "chat.py") -> None:
        """
        Initialize the ConversationFlowTester.

        Sets up the OpenShift client and initializes conversation history.

        Args:
            test_script: Name of the test script to execute (default: "chat.py")
        """
        self.client = OpenShiftChatClient(test_script=test_script)
        self.conversation_history = []
        self.total_app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}

    def run_flow(self, questions) -> List[Dict[str, str]]:
        """
        Run a conversation flow with the given questions.

        Starts a session with the agent, sends each question in sequence,
        and collects the responses. Returns the complete conversation.

        Args:
            questions: List of questions/messages to send to the agent

        Returns:
            List of conversation turns with role and content for each message

        Raises:
            Exception: If there are issues with the OpenShift session or communication
        """
        conversation = []

        try:
            self.client.start_session()

            # First, get the agent initialization message
            agent_init = self.client.get_agent_initialization()
            conversation.append({"role": "assistant", "content": agent_init})

            # Then process user questions
            for i, question in enumerate(questions):
                response = self.client.send_message(question)

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
                if self.client.session_active:
                    logger.debug("Attempting to request token summary from agent...")
                    # This will work when chat-lg-state.py includes the **tokens** command
                    token_response = self.client.send_message("**tokens**")
                    logger.debug(f"Token request response: {token_response}")
            except Exception as e:
                logger.debug(f"Token request not supported by current deployment: {e}")

            self.client.close_session()

            # Collect app tokens from this conversation
            app_tokens = self.client.get_app_tokens()
            logger.info(f"App tokens from conversation: {app_tokens}")
            logger.info(
                f"Session captured {len(self.client.session_output)} lines of output"
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

                # Extract questions from the conversation data
                # Assuming the conversation is a list of role/content dictionaries
                questions = []
                for turn in conversation_data:
                    if isinstance(turn, dict) and turn.get("role") == "user":
                        questions.append(turn.get("content", ""))

                if not questions:
                    logger.warning(f"No user questions found in {filename}")
                    continue

                logger.info(f"Processing {filename} with {len(questions)} questions")

                # Run the flow with extracted questions
                results = self.run_flow(questions)

                # Save results to output directory
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

                logger.info(f"Results saved to {output_path}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON in {filename}: {e}")
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")

        logger.info("Flows processing completed")

        # Print token usage summary with separate app and evaluation tokens
        print("\n=== Token Usage Summary ===")

        # Get evaluation token stats
        eval_stats = get_token_stats()

        # Display app tokens (from chat-lg-state.py via oc exec)
        print("\n📱 App Tokens (from chat agent):")
        print(f"  Input tokens: {self.total_app_tokens['input']:,}")
        print(f"  Output tokens: {self.total_app_tokens['output']:,}")
        print(f"  Total tokens: {self.total_app_tokens['total']:,}")
        print(f"  API calls: {self.total_app_tokens['calls']:,}")

        # Display evaluation tokens (from evaluation LLM calls)
        print("\n🔬 Evaluation Tokens (from evaluation LLM calls):")
        print(f"  Input tokens: {eval_stats.total_input_tokens:,}")
        print(f"  Output tokens: {eval_stats.total_output_tokens:,}")
        print(f"  Total tokens: {eval_stats.total_tokens:,}")
        print(f"  API calls: {eval_stats.call_count:,}")

        # Display combined totals
        combined_input = self.total_app_tokens["input"] + eval_stats.total_input_tokens
        combined_output = (
            self.total_app_tokens["output"] + eval_stats.total_output_tokens
        )
        combined_total = self.total_app_tokens["total"] + eval_stats.total_tokens
        combined_calls = self.total_app_tokens["calls"] + eval_stats.call_count

        print("\n📊 Combined Totals:")
        print(f"  Input tokens: {combined_input:,}")
        print(f"  Output tokens: {combined_output:,}")
        print(f"  Total tokens: {combined_total:,}")
        print(f"  API calls: {combined_calls:,}")

        # Save token stats to file
        if eval_stats.call_count > 0 or self.total_app_tokens["calls"] > 0:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            token_dir = "results/token_usage"
            token_file = os.path.join(token_dir, f"run_conversations_{timestamp}.json")

            # Create comprehensive token data including app and evaluation tokens
            comprehensive_stats = {
                "summary": {
                    "total_input_tokens": combined_input,
                    "total_output_tokens": combined_output,
                    "total_tokens": combined_total,
                    "call_count": combined_calls,
                },
                "app_tokens": self.total_app_tokens,
                "evaluation_tokens": {
                    "total_input_tokens": eval_stats.total_input_tokens,
                    "total_output_tokens": eval_stats.total_output_tokens,
                    "total_tokens": eval_stats.total_tokens,
                    "call_count": eval_stats.call_count,
                },
                "detailed_calls": getattr(eval_stats, "detailed_calls", []),
            }

            os.makedirs(token_dir, exist_ok=True)
            with open(token_file, "w") as f:
                json.dump(comprehensive_stats, f, indent=2)
            print(f"Token usage saved to: {token_file}")
