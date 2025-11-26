#!/usr/bin/env python3
"""
Request Manager client library for the self-service agent quickstart.

This module provides reusable client classes for interacting with the Request Manager
service, including both generic and CLI-specific implementations.
"""

import logging
import os
import uuid
from typing import Any, Dict, Optional, Union

import httpx
from shared_models import configure_logging

# Remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = configure_logging("request-manager-client")

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")


class RequestManagerClient:
    """Base client for interacting with the Request Manager service."""

    def __init__(
        self,
        request_manager_url: str | None = None,
        user_id: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        """
        Initialize the Request Manager client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
        """
        self.request_manager_url = request_manager_url or os.getenv(
            "REQUEST_MANAGER_URL", "http://localhost:8080"
        )
        self.user_id = user_id or str(uuid.uuid4())
        self.client = httpx.AsyncClient(
            timeout=timeout,
            # Performance optimizations
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            http2=True,  # Enable HTTP/2 for better performance
            headers={"Accept-Encoding": "gzip, deflate, br"},  # Enable compression
        )

    def _format_response(self, result: dict[str, Any]) -> str:
        """Format the response."""
        # Check if result is the response object directly
        # or wrapped in a "response" key
        if "content" in result and "agent_id" in result:
            # Result is the response object directly
            content = result.get("content")
            return str(content) if content is not None else "No response content"
        else:
            # Result is wrapped in a "response" key
            response_data = result.get("response", {})
            content = response_data.get("content")
            return str(content) if content is not None else "No response content"

    async def send_request(
        self,
        content: str,
        integration_type: str = "CLI",
        request_type: str = "message",
        metadata: Optional[Dict[str, Any]] = None,
        endpoint: str = "generic",
    ) -> Dict[str, Any]:
        """
        Send a request to the Request Manager service.

        Args:
            content: The message content to send
            integration_type: Type of integration (CLI, WEB, SLACK, etc.)
            request_type: Type of request (message, command, etc.)
            metadata: Additional metadata for the request
            endpoint: API endpoint to use (generic, cli, web, etc.)

        Returns:
            Response dictionary containing session_id, response content, etc.

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        payload = {
            "user_id": self.user_id,
            "content": content,
            "integration_type": integration_type,
            "request_type": request_type,
            "metadata": metadata or {},
        }

        headers = {"x-user-id": self.user_id}

        response = await self.client.post(
            f"{self.request_manager_url}/api/v1/requests/{endpoint}",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        # Parse response

        try:
            result = response.json()
            return (
                result
                if isinstance(result, dict)
                else {"error": "Invalid JSON response format"}
            )
        except Exception as e:
            # Return the raw text if JSON parsing fails
            return {
                "error": f"Failed to parse JSON response: {e}",
                "raw_response": response.text,
            }

    async def get_request_status(self, request_id: str) -> Dict[str, Any]:
        """
        Get the status of a specific request.

        Args:
            request_id: The request ID to check

        Returns:
            Request status dictionary

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        headers = {"x-user-id": self.user_id}
        response = await self.client.get(
            f"{self.request_manager_url}/api/v1/requests/{request_id}",
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()
        return (
            result
            if isinstance(result, dict)
            else {"error": "Invalid JSON response format"}
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


class CLIChatClient(RequestManagerClient):
    """CLI-specific chat client using Request Manager."""

    def __init__(
        self,
        request_manager_url: str | None = None,
        user_id: str | None = None,
        timeout: float = 120.0,  # Reduced from 180s for better performance
        **kwargs: Any,
    ) -> None:
        """
        Initialize the CLI chat client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(request_manager_url, user_id, timeout, **kwargs)

    async def send_message(
        self,
        message: str,
        command_context: Optional[Dict[str, Any]] = None,
        request_manager_session_id: Optional[str] = None,
        user_email: Optional[str] = None,
        session_name: Optional[str] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Send a message to the agent via Request Manager.

        Args:
            message: The message to send
            command_context: CLI command context (default: {"command": "chat", "args": []})
            request_manager_session_id: Session ID (auto-generated if not provided)
            user_email: User email
            session_name: Session name

        Returns:
            Agent response content string

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        if command_context is None:
            command_context = {"command": "chat", "args": []}

        if not request_manager_session_id:
            request_manager_session_id = str(uuid.uuid4())

        metadata: Dict[str, Any] = {
            "command_context": command_context,
            "request_manager_session_id": request_manager_session_id,
            "user_email": user_email or "",
            "session_name": session_name or "",
        }

        request_url = f"{self.request_manager_url}/api/v1/requests/generic"
        logger.debug(
            "Sending request to Request Manager",
            url=request_url,
            payload=message,
        )

        try:
            result = await self.send_request(
                content=message,
                integration_type="CLI",
                request_type="message",
                metadata=metadata,
                endpoint="generic",
            )

            logger.debug(
                "Received result from Request Manager",
                result_type=type(result).__name__,
                result=result,
            )

            return self._format_response(result)

        except httpx.ConnectError as e:
            return f"Error connecting to Request Manager at {self.request_manager_url}: {e}"
        except httpx.HTTPError as e:
            return f"Error communicating with Request Manager: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def reset_session(self) -> None:
        """Reset the current session."""
        # For now, just generate a new user_id to effectively reset the session
        self.user_id = str(uuid.uuid4())

    async def _process_message(self, message: str, test_mode: bool) -> bool:
        """
        Process a single message and return True if the chat loop should continue.

        Returns:
            bool: True if chat should continue, False if it should break
        """
        if message.lower() in ["quit", "exit"] or (
            not test_mode and message.lower() == "q"
        ):
            return False
        elif message.lower() == "**tokens**":
            agent_response = await self.send_message(message)
            # Extract string content from response
            if isinstance(agent_response, dict):
                response_content = agent_response.get("content", str(agent_response))
            else:
                response_content = agent_response
            self._handle_tokens_command(response_content)
            return False
        elif message.strip():
            agent_response = await self.send_message(message)
            print(f"agent: {agent_response}")
            if test_mode:
                print(AGENT_MESSAGE_TERMINATOR)

        return True

    def _handle_tokens_command(self, agent_response: str) -> None:
        """Handle the **tokens** command by extracting and formatting token summary."""
        if "TOKEN_SUMMARY:" in agent_response:
            # Extract the token summary line
            lines = agent_response.split("\n")
            token_summary_line = None
            for line in lines:
                if line.startswith("TOKEN_SUMMARY:"):
                    token_summary_line = line
                    break

            if token_summary_line:
                self._format_token_summary(token_summary_line)
        else:
            print(agent_response)

    def _format_token_summary(self, token_summary_line: str) -> None:
        """Format and print token summary."""
        # Parse the token summary to create formatted output
        # Format: TOKEN_SUMMARY:INPUT:1100:OUTPUT:590:TOTAL:1690:CALLS:6:MAX_SINGLE_INPUT:236:MAX_SINGLE_OUTPUT:184:MAX_SINGLE_TOTAL:348
        parts = token_summary_line.split(":")
        if len(parts) >= 8:
            input_tokens = int(parts[2])
            output_tokens = int(parts[4])
            total_tokens = int(parts[6])
            calls = int(parts[8])
            max_input = int(parts[10])
            max_output = int(parts[12])
            max_total = int(parts[14])

            # Print the formatted summary
            print(
                f"CURRENT_TOKEN_SUMMARY:INPUT:{input_tokens}:OUTPUT:{output_tokens}:TOTAL:{total_tokens}:CALLS:{calls}:MAX_SINGLE_INPUT:{max_input}:MAX_SINGLE_OUTPUT:{max_output}:MAX_SINGLE_TOTAL:{max_total}"
            )
            print("TOKEN_SUMMARY_END")
            print()
            print("bye!")

            # Show session name for resuming conversation
            if hasattr(self, "session_id") and self.session_id:
                print(
                    f"To resume this conversation, use: --session-name {self.session_id}"
                )

            # Print formatted token usage summary
            print("\n" + "=" * 50)
            print("  Total Token Usage Summary:")
            print(f"    Total calls: {calls}")
            print(f"    Input tokens: {input_tokens:,}")
            print(f"    Output tokens: {output_tokens:,}")
            print(f"    Total tokens: {total_tokens:,}")
            print(f"    Max single request input: {max_input}")
            print(f"    Max single request output: {max_output}")
            print(f"    Max single request total: {max_total}")
            if calls > 0:
                avg_input = input_tokens / calls
                avg_output = output_tokens / calls
                avg_total = total_tokens / calls
                print(
                    f"    Average per call: {avg_input:.1f} input, {avg_output:.1f} output, {avg_total:.1f} total"
                )
            print("=" * 50)

            # Print machine-readable token counts
            print(token_summary_line)
            print("TOKEN_SUMMARY_END")

    async def chat_loop(
        self,
        initial_message: str | None = None,
        test_mode: bool = False,
    ) -> None:
        """
        Run a chat loop for interactive or automated testing.

        Args:
            initial_message: Optional initial message to send
            test_mode: If True, reads from stdin for automated testing
        """
        if test_mode:
            logger.debug(
                "Test mode chat loop started",
                request_manager_url=self.request_manager_url,
                user_id=self.user_id,
            )
        else:
            print("CLI Chat - Type 'quit' to exit, 'reset' to clear session")
            print(f"Using Request Manager at: {self.request_manager_url}")

        # Send initial greeting if provided
        if initial_message:
            logger.debug("Sending initial message", message=initial_message)
            try:
                agent_response = await self.send_message(initial_message)
                print(f"agent: {agent_response}")
                if test_mode:
                    print(AGENT_MESSAGE_TERMINATOR)
            except Exception as e:
                if test_mode:
                    print(f"Error sending initial message: {e}")
                    return
                else:
                    print(f"Error: {e}")

        # Main message processing loop
        if test_mode:
            # Test mode: read from stdin
            try:
                import sys

                for line in sys.stdin:
                    message = line.strip()
                    if not message:
                        continue

                    should_continue = await self._process_message(
                        message, test_mode=True
                    )
                    if not should_continue:
                        break

            except EOFError:
                # End of input stream
                pass
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                pass
        else:
            # Interactive mode: use input()
            while True:
                try:
                    message = input("> ")
                    should_continue = await self._process_message(
                        message, test_mode=False
                    )
                    if not should_continue:
                        break

                except KeyboardInterrupt:
                    break

        await self.close()

    async def chat_loop_test_mode(
        self,
        initial_message: str | None = None,
    ) -> None:
        """
        Run a test-mode chat loop that reads from stdin for automated testing.
        This is a convenience wrapper around chat_loop with test_mode=True.

        Args:
            initial_message: Optional initial message to send
        """
        await self.chat_loop(initial_message=initial_message, test_mode=True)
