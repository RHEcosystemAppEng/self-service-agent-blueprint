#!/usr/bin/env python3

import logging
import subprocess
import time
from typing import List

logger = logging.getLogger(__name__)

AGENT_MESSAGE_TERMINATOR = ":DONE"


class OpenShiftChatClient:
    """Client for interacting with the self-service agent via OpenShift exec"""

    def __init__(
        self,
        deployment_name: str = "deploy/self-service-agent",
        test_script: str = "chat.py",
    ):
        """
        Initialize the OpenShift chat client.

        Args:
            deployment_name: Name of the OpenShift deployment to connect to
            test_script: Name of the test script to execute (default: "chat.py")
        """
        self.deployment_name = deployment_name
        self.test_script = test_script
        self.process = None
        self.session_active = False

    def start_session(self) -> None:
        """
        Start an interactive session with the chat client.

        Creates a subprocess that executes the chat.py script inside the
        OpenShift pod via 'oc exec'. Sets up stdin/stdout pipes for
        communication and marks the session as active.

        Raises:
            subprocess.CalledProcessError: If the oc exec command fails
            Exception: If there are other issues starting the session
        """
        try:
            cmd = [
                "oc",
                "exec",
                "-it",
                "deploy/self-service-agent",
                "--",
                "bash",
                "-c",
                f"AGENT_MESSAGE_TERMINATOR={AGENT_MESSAGE_TERMINATOR} /app/.venv/bin/python {'/app/test/' + self.test_script if not self.test_script.startswith('/') else self.test_script}",
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

        Returns:
            The agent's initialization message as a string

        Raises:
            RuntimeError: If the session is not active
        """
        if not self.session_active or not self.process:
            raise RuntimeError("Session not active. Call start_session() first.")

        agent_message = self._read_full_agent_message()
        logger.debug(f"Agent initialization: {agent_message[:100]}...")
        return agent_message

    def send_message(self, message: str, timeout: int = 30) -> str:
        """
        Send a message to the agent and get the response.

        Sends the message to the agent via stdin and waits for a complete
        response. The response is read until the AGENT_MESSAGE_TERMINATOR
        is encountered.

        Args:
            message: The message to send to the agent
            timeout: Maximum time to wait for response in seconds

        Returns:
            The agent's response as a string

        Raises:
            RuntimeError: If the session is not active
            Exception: If there are communication errors
        """
        if not self.session_active or not self.process:
            raise RuntimeError("Session not active. Call start_session() first.")

        try:
            self.process.stdin.write(message + "\n")
            self.process.stdin.flush()

            response = self._read_full_agent_message(timeout)

            logger.debug(f"Sent: {message}")
            logger.debug(
                f"Received: {response[:200]}{'...' if len(response) > 200 else ''}"
            )

            if not response:
                logger.warning("Received empty response")

            return response

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return ""

    def _read_full_agent_message(self, timeout: int = 30) -> str:
        """
        Read a complete agent message between 'agent:' and AGENT_MESSAGE_TERMINATOR markers.

        Reads from the agent's stdout until a complete message is received.
        Messages start with 'agent:' and end with AGENT_MESSAGE_TERMINATOR.

        Args:
            timeout: Maximum time to wait for a complete message in seconds

        Returns:
            The complete agent message with markers removed
        """
        response_parts: List[str] = []
        start_time = time.time()
        agent_started = False

        while time.time() - start_time < timeout:
            if self.process.poll() is not None:
                break

            try:
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                s = line.strip()

                if not agent_started:
                    start_idx = s.find("agent:")
                    if start_idx == -1:
                        continue
                    agent_started = True
                    s = s[start_idx + len("agent:") :].strip()

                end_idx = s.find(AGENT_MESSAGE_TERMINATOR)
                if end_idx != -1:
                    part = s[:end_idx].strip()
                    if part:
                        response_parts.append(part)
                    break
                else:
                    if s:
                        response_parts.append(s)

            except Exception as e:
                logger.debug(f"Read error: {e}")
                time.sleep(0.1)
                continue

        return "\n".join(response_parts).strip()

    def close_session(self) -> None:
        """
        Close the chat session.

        Terminates the subprocess running the chat client. Attempts a
        graceful termination first, then forces termination if needed.
        Marks the session as inactive and cleans up resources.
        """
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            finally:
                self.process = None
                self.session_active = False
                logger.debug("Closed OpenShift chat session")
