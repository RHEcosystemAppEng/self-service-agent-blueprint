#!/usr/bin/env python3
"""
Request Manager client library for the self-service agent blueprint.

This module provides reusable client classes for interacting with the Request Manager
service, including both generic and CLI-specific implementations.
"""

import logging
import os
import uuid
from typing import Any, Dict, Optional, Union

import httpx

# Remove logging we otherwise get by default
logging.getLogger("httpx").setLevel(logging.WARNING)

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")


class RequestManagerClient:
    """Base client for interacting with the Request Manager service."""

    def __init__(
        self,
        request_manager_url: str = None,
        user_id: str = None,
        timeout: float = 180.0,
        use_responses: bool = False,
    ):
        """
        Initialize the Request Manager client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
            use_responses: Enable responses API mode (LangGraph-based conversations)
        """
        self.request_manager_url = request_manager_url or os.getenv(
            "REQUEST_MANAGER_URL", "http://localhost:8080"
        )
        self.user_id = user_id or str(uuid.uuid4())
        self.use_responses = use_responses
        self.client = httpx.AsyncClient(
            timeout=timeout,
            # Performance optimizations
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            http2=True,  # Enable HTTP/2 for better performance
            headers={"Accept-Encoding": "gzip, deflate, br"},  # Enable compression
        )

    def _format_response(self, result: dict) -> str:
        """Format the response based on the mode."""
        if self.use_responses:
            # For responses mode, check if result is the response object directly
            # or wrapped in a "response" key
            if "content" in result and "agent_id" in result:
                # Result is the response object directly
                return result.get("content", "No response content")
            else:
                # Result is wrapped in a "response" key
                response_data = result.get("response", {})
                return response_data.get("content", "No response content")
        else:
            # For traditional agents mode, extract just the content
            response_data = result.get("response", {})
            return response_data.get("content", "No response content")

    async def send_request(
        self,
        content: str,
        integration_type: str = "CLI",
        request_type: str = "message",
        metadata: Optional[Dict[str, Any]] = None,
        endpoint: str = "generic",
        use_responses: bool = None,
    ) -> Dict[str, Any]:
        """
        Send a request to the Request Manager service.

        Args:
            content: The message content to send
            integration_type: Type of integration (CLI, WEB, SLACK, etc.)
            request_type: Type of request (message, command, etc.)
            metadata: Additional metadata for the request
            endpoint: API endpoint to use (generic, cli, web, etc.)
            use_responses: Override client-level use_responses setting (None = use client default)

        Returns:
            Response dictionary containing session_id, response content, etc.

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        # Use client-level use_responses if not explicitly overridden
        if use_responses is None:
            use_responses = self.use_responses

        payload = {
            "user_id": self.user_id,
            "content": content,
            "integration_type": integration_type,
            "request_type": request_type,
            "metadata": metadata or {},
            "use_responses": use_responses,
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
            return response.json()
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
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class CLIChatClient(RequestManagerClient):
    """CLI-specific chat client using Request Manager."""

    def __init__(
        self,
        request_manager_url: str = None,
        user_id: str = None,
        timeout: float = 120.0,  # Reduced from 180s for better performance
        **kwargs,
    ):
        """
        Initialize the CLI chat client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
            **kwargs: Additional arguments passed to parent class (including use_responses)
        """
        super().__init__(request_manager_url, user_id, timeout, **kwargs)

    async def send_message(
        self,
        message: str,
        command_context: Optional[Dict[str, Any]] = None,
        debug: bool = False,
        request_manager_session_id: Optional[str] = None,
        user_email: Optional[str] = None,
        session_name: Optional[str] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Send a message to the agent via Request Manager.

        Args:
            message: The message to send
            command_context: CLI command context (default: {"command": "chat", "args": []})
            debug: Whether to print debug information
            request_manager_session_id: Session ID for responses mode (auto-generated if not provided)
            user_email: User email for responses mode
            session_name: Session name for responses mode

        Returns:
            Full response dictionary for use_responses=True, agent response content string for use_responses=False

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        if command_context is None:
            command_context = {"command": "chat", "args": []}

        metadata = {
            "command_context": command_context,
        }

        # For responses mode, add session metadata
        if self.use_responses:
            if not request_manager_session_id:
                request_manager_session_id = str(uuid.uuid4())
            metadata.update(
                {
                    "request_manager_session_id": request_manager_session_id,
                    "user_email": user_email,
                    "session_name": session_name,
                }
            )

        if debug:
            print(
                f"DEBUG: Sending request to {self.request_manager_url}/api/v1/requests/generic"
            )
            print(f"DEBUG: Payload: {message}")
            print(f"DEBUG: Use responses: {self.use_responses}")

        try:
            result = await self.send_request(
                content=message,
                integration_type="CLI",
                request_type="message",
                metadata=metadata,
                endpoint="generic",
                use_responses=self.use_responses,
            )

            if debug:
                print(f"DEBUG: Result type: {type(result)}")
                print(f"DEBUG: Result: {result}")

            return self._format_response(result)

        except httpx.ConnectError as e:
            return f"Error connecting to Request Manager at {self.request_manager_url}: {e}"
        except httpx.HTTPError as e:
            return f"Error communicating with Request Manager: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def reset_session(self):
        """Reset the current session."""
        # For now, just generate a new user_id to effectively reset the session
        self.user_id = str(uuid.uuid4())

    async def chat_loop(
        self,
        initial_message: str = None,
        debug: bool = False,
    ):
        """
        Run an interactive chat loop.

        Args:
            initial_message: Optional initial message to send
            debug: Whether to print debug information
        """
        print("CLI Chat - Type 'quit' to exit, 'reset' to clear session")
        print(f"Using Request Manager at: {self.request_manager_url}")

        # Send initial greeting if provided
        if initial_message:
            agent_response = await self.send_message(initial_message, debug=debug)
            print(f"agent: {agent_response}")

        while True:
            try:
                message = input("> ")
                if message.lower() in ["quit", "exit", "q"]:
                    break

                if message.strip():
                    agent_response = await self.send_message(message, debug=debug)
                    print(f"agent: {agent_response}")

            except KeyboardInterrupt:
                break

        await self.close()

    async def chat_loop_test_mode(
        self,
        initial_message: str = None,
        debug: bool = False,
    ):
        """
        Run a test-mode chat loop that reads from stdin for automated testing.

        Args:
            initial_message: Optional initial message to send
            debug: Whether to print debug information
        """
        if debug:
            print("DEBUG: Test mode chat loop started")
            print(f"DEBUG: Using Request Manager at: {self.request_manager_url}")
            print(f"DEBUG: User ID: {self.user_id}")

        # Send initial greeting if provided
        if initial_message:
            if debug:
                print(f"DEBUG: Sending initial message: {initial_message}")
            try:
                agent_response = await self.send_message(initial_message, debug=debug)
                print(f"agent: {agent_response}")
                print(AGENT_MESSAGE_TERMINATOR)
            except Exception as e:
                print(f"Error sending initial message: {e}")
                return

        # Read messages from stdin for automated testing
        try:
            import sys

            for line in sys.stdin:
                message = line.strip()
                if not message:
                    continue

                if message.lower() in ["quit", "exit"]:
                    break

                agent_response = await self.send_message(message, debug=debug)
                print(f"agent: {agent_response}")
                print(AGENT_MESSAGE_TERMINATOR)

        except EOFError:
            # End of input stream
            pass
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            pass
        finally:
            await self.close()
