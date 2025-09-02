#!/usr/bin/env python3
"""
Request Manager client library for the self-service agent blueprint.

This module provides reusable client classes for interacting with the Request Manager
service, including both generic and CLI-specific implementations.
"""

import logging
import os
import uuid
from typing import Any, Dict, Optional

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
    ):
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

    async def send_request(
        self,
        content: str,
        integration_type: str = "CLI",
        request_type: str = "message",
        metadata: Optional[Dict[str, Any]] = None,
        endpoint: str = "generic/sync",
    ) -> Dict[str, Any]:
        """
        Send a request to the Request Manager service.

        Args:
            content: The message content to send
            integration_type: Type of integration (CLI, WEB, SLACK, etc.)
            request_type: Type of request (message, command, etc.)
            metadata: Additional metadata for the request
            endpoint: API endpoint to use (generic/sync, cli, web, etc.)

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
        return response.json()

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
    ):
        """
        Initialize the CLI chat client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
        """
        super().__init__(request_manager_url, user_id, timeout)

    async def send_message(
        self,
        message: str,
        command_context: Optional[Dict[str, Any]] = None,
        debug: bool = False,
    ) -> str:
        """
        Send a message to the agent via Request Manager.

        Args:
            message: The message to send
            command_context: CLI command context (default: {"command": "chat", "args": []})
            debug: Whether to print debug information

        Returns:
            Agent response content

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        if command_context is None:
            command_context = {"command": "chat", "args": []}

        metadata = {
            "command_context": command_context,
        }

        if debug:
            print(
                f"DEBUG: Sending request to {self.request_manager_url}/api/v1/requests/generic/sync"
            )
            print(f"DEBUG: Payload: {message}")

        try:
            result = await self.send_request(
                content=message,
                integration_type="CLI",
                request_type="message",
                metadata=metadata,
                endpoint="generic/sync",
            )

            # Extract response content
            response_data = result.get("response", {})
            return response_data.get("content", "No response content")

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

    async def chat_loop(self, initial_message: str = None, debug: bool = False):
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
        print("\nbye!")

    async def chat_loop_test_mode(
        self, initial_message: str = None, debug: bool = False
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

                if message.lower() == "reset":
                    await self.reset_session()
                    print("Session reset")
                    continue

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
