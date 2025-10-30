#!/usr/bin/env python3

import logging
import os
import subprocess
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

AGENT_MESSAGE_TERMINATOR = ":DONE"


class OpenShiftChatClient:
    """Client for interacting with the self-service agent via OpenShift exec"""

    def __init__(
        self,
        authoritative_user_id: str,
        deployment_name: str = "deploy/self-service-agent-request-manager",
        test_script: str = "chat-responses-request-mgr.py",
        reset_conversation: bool = False,
        message_timeout: int = 60,
    ):
        """
        Initialize the OpenShift chat client.

        Args:
            authoritative_user_id: Required user ID to set as AUTHORITATIVE_USER_ID environment variable
            deployment_name: Name of the OpenShift deployment to connect to
            test_script: Name of the test script to execute (default: "chat-responses-request-mgr.py")
            reset_conversation: If True, send "reset" message after initialization
            message_timeout: Timeout in seconds for individual message send/response operations (default: 60)
        """
        self.deployment_name = deployment_name
        self.test_script = test_script
        self.authoritative_user_id = authoritative_user_id
        self.reset_conversation = reset_conversation
        self.message_timeout = message_timeout
        self.process: Optional[subprocess.Popen[str]] = None
        self.session_active = False
        self.session_output: list[str] = []  # Capture all output for token parsing
        self.app_tokens = {
            "input": 0,
            "output": 0,
            "total": 0,
            "calls": 0,
            "max_input": 0,
            "max_output": 0,
            "max_total": 0,
        }

    def start_session(self) -> None:
        """
        Start an interactive session with the chat client.

        Creates a subprocess that executes the chat script inside the
        OpenShift pod via 'oc exec'. Sets up stdin/stdout pipes for
        communication and marks the session as active.

        Raises:
            subprocess.CalledProcessError: If the oc exec command fails
            Exception: If there are other issues starting the session
        """
        try:
            # Build environment variables string
            env_vars = f"AGENT_MESSAGE_TERMINATOR={AGENT_MESSAGE_TERMINATOR}"
            env_vars += f" AUTHORITATIVE_USER_ID={self.authoritative_user_id}"

            # Set PYTHONPATH if TEST_MODE is enabled
            if os.environ.get("TEST_MODE"):
                env_vars += " PYTHONPATH=/opt/app-root/agent-service/src:/opt/app-root/slack-service/src:/opt/app-root/session-manager/src:"

            cmd = [
                "oc",
                "exec",
                "-it",
                "deploy/self-service-agent-request-manager",
                "--",
                "bash",
                "-c",
                f"{env_vars} /app/.venv/bin/python {'/app/test/' + self.test_script if not self.test_script.startswith('/') else self.test_script}",
            ]
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            time.sleep(2)
            self.session_active = True
            logger.debug("Started OpenShift chat session")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start OpenShift session: {e}")
            raise

    def get_agent_initialization(self) -> str:
        """
        Wait for and capture the agent's initialization message.

        Reads the initial message sent by the agent when the session starts.
        This is typically a greeting or instructions for the user.
        If reset_conversation is True, sends "reset" message after initialization.

        Returns:
            The agent's initialization message as a string

        Raises:
            RuntimeError: If the session is not active
        """
        if not self.session_active or not self.process:
            raise RuntimeError("Session not active. Call start_session() first.")

        agent_message = self._read_full_agent_message()
        logger.debug(f"Agent initialization: {agent_message[:100]}...")

        # Send reset message if requested
        if self.reset_conversation:
            logger.info("Sending reset message to start fresh conversation")
            reset_response = self.send_message("reset")
            logger.info(
                f"Reset response: {reset_response[:100] if reset_response else 'empty'}..."
            )

            # After reset, ask for introduction
            logger.info("Requesting agent introduction after reset")
            intro_response = self.send_message(
                "please introduce yourself and tell me how you can help"
            )
            logger.info(
                f"Introduction response: {intro_response[:100] if intro_response else 'empty'}..."
            )

            # Return the introduction response instead of the original initialization
            return intro_response

        return agent_message

    def send_message(self, message: str, timeout: Optional[int] = None) -> str:
        """
        Send a message to the agent and get the response.

        Sends the message to the agent via stdin and waits for a complete
        response. The response is read until the AGENT_MESSAGE_TERMINATOR
        is encountered.

        Args:
            message: The message to send to the agent
            timeout: Maximum time to wait for response in seconds (default: uses self.message_timeout)

        Returns:
            The agent's response as a string

        Raises:
            RuntimeError: If the session is not active
            Exception: If there are communication errors
        """
        if not self.session_active or not self.process:
            raise RuntimeError("Session not active. Call start_session() first.")

        # Use instance timeout if not specified
        if timeout is None:
            timeout = self.message_timeout

        try:
            if self.process.stdin is not None:
                self.process.stdin.write(message + "\n")
                self.process.stdin.flush()

            response = self._read_full_agent_message(timeout)

            logger.debug(f"Sent: {message}")
            logger.debug(
                f"Received: {response[:200]}{'...' if len(response) > 200 else ''}"
            )

            if not response:
                logger.warning(f"Received empty response for message: {message[:100]}")

            return response

        except Exception as e:
            logger.error(f"Error sending message: {e}, message: {message}")
            return ""

    def _read_full_agent_message(self, timeout: Optional[int] = None) -> str:
        """
        Read a complete agent message between 'agent:' and AGENT_MESSAGE_TERMINATOR markers.

        Reads from the agent's stdout until a complete message is received.
        Messages start with 'agent:' and end with AGENT_MESSAGE_TERMINATOR.

        Args:
            timeout: Maximum time to wait for a complete message in seconds (default: uses self.message_timeout)

        Returns:
            The complete agent message with markers removed. If timeout occurs,
            appends a clear timeout indicator to the partial response.
        """
        # Use instance timeout if not specified
        if timeout is None:
            timeout = self.message_timeout
        response_parts: List[str] = []
        start_time = time.time()
        agent_started = False
        lines_read = 0
        timed_out = False

        while time.time() - start_time < timeout:
            if self.process is not None and self.process.poll() is not None:
                logger.debug("Process terminated while reading message")
                break

            try:
                if self.process is not None and self.process.stdout is not None:
                    line = self.process.stdout.readline()
                else:
                    line = ""
                if not line:
                    time.sleep(0.1)
                    continue

                s = line.strip()
                lines_read += 1

                # Capture all output for potential token parsing
                self.session_output.append(s)

                # Check for token summary output
                self._parse_token_output(s)

                if not agent_started:
                    start_idx = s.find("agent:")
                    if start_idx == -1:
                        continue
                    agent_started = True
                    s = s[start_idx + len("agent:") :].strip()
                    logger.debug(
                        f"Agent message started, read {lines_read} lines to get here"
                    )

                end_idx = s.find(AGENT_MESSAGE_TERMINATOR)
                if end_idx != -1:
                    part = s[:end_idx].strip()
                    if part:
                        response_parts.append(part)
                    logger.debug(
                        f"Agent message completed after {lines_read} total lines"
                    )
                    break
                else:
                    if s:
                        response_parts.append(s)

            except Exception as e:
                logger.debug(f"Read error: {e}")
                time.sleep(0.1)
                continue

        if time.time() - start_time >= timeout:
            timed_out = True
            partial_response = "\n".join(response_parts).strip()
            logger.warning(
                f"Timeout reading agent message after {timeout}s, read {lines_read} lines, agent_started={agent_started}, "
                f"partial_response_length={len(partial_response)}, "
                f"partial_response_preview={partial_response[:200] if partial_response else 'EMPTY'}"
            )

        result = "\n".join(response_parts).strip()

        # If timeout occurred, append a clear indicator to the response
        # This ensures it shows up in the recorded conversation
        if timed_out:
            timeout_marker = f"\n\n[TIMEOUT: Response incomplete after {timeout}s timeout. This is a partial response.]"
            result = (
                result + timeout_marker
                if result
                else f"[TIMEOUT: No response received after {timeout}s timeout.]"
            )

        return result

    def _parse_token_output(self, line: str) -> None:
        """
        Parse token summary output from chat-lg-state.py.

        Looks for lines in format:
        TOKEN_SUMMARY:INPUT:123:OUTPUT:456:TOTAL:579:CALLS:2:MAX_SINGLE_INPUT:50:MAX_SINGLE_OUTPUT:75:MAX_SINGLE_TOTAL:125

        Args:
            line: Output line to check for token information
        """
        if line.startswith("TOKEN_SUMMARY:") or line.startswith(
            "CURRENT_TOKEN_SUMMARY:"
        ):
            try:
                # Parse extended format with maximum values
                parts = line.split(":")
                if len(parts) >= 8:
                    self.app_tokens["input"] = int(parts[2])
                    self.app_tokens["output"] = int(parts[4])
                    self.app_tokens["total"] = int(parts[6])
                    self.app_tokens["calls"] = int(parts[8])

                    # Parse maximum values if present (new format)
                    if len(parts) >= 14:
                        self.app_tokens["max_input"] = int(
                            parts[10]
                        )  # MAX_SINGLE_INPUT
                        self.app_tokens["max_output"] = int(
                            parts[12]
                        )  # MAX_SINGLE_OUTPUT
                        self.app_tokens["max_total"] = int(
                            parts[14]
                        )  # MAX_SINGLE_TOTAL
                    else:
                        # Legacy format without maximums
                        self.app_tokens["max_input"] = 0
                        self.app_tokens["max_output"] = 0
                        self.app_tokens["max_total"] = 0

                    logger.info(f"Successfully parsed app tokens: {self.app_tokens}")
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse token output '{line}': {e}")

    def get_app_tokens(self) -> Dict[str, int]:
        """
        Get the app tokens collected from the session.

        Returns:
            Dictionary with input, output, total, and calls counts
        """
        return self.app_tokens.copy()

    def close_session(self) -> None:
        """
        Close the chat session.

        Terminates the subprocess running the chat client. Attempts a
        graceful termination first, then forces termination if needed.
        Marks the session as inactive and cleans up resources.
        """
        if self.process:
            try:
                # Try to read any remaining output before terminating
                # This might contain token summary information
                import select

                # Set a short timeout to capture any remaining output
                remaining_output = []
                try:
                    if hasattr(select, "select") and self.process.stdout:
                        # Non-blocking read for remaining output
                        ready, _, _ = select.select([self.process.stdout], [], [], 2.0)
                        if ready:
                            while True:
                                line = self.process.stdout.readline()
                                if not line:
                                    break
                                s = line.strip()
                                remaining_output.append(s)
                                self.session_output.append(s)
                                self._parse_token_output(s)
                                if s == "TOKEN_SUMMARY_END":
                                    break
                except Exception as e:
                    logger.debug(f"Error reading remaining output: {e}")

                self.process.terminate()
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            finally:
                self.process = None
                self.session_active = False
                logger.debug("Closed OpenShift chat session")
