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
        self.client = httpx.AsyncClient(timeout=timeout)

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

    async def update_session(
        self, session_id: str, session_update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a session.

        Args:
            session_id: The session ID to update
            session_update: Session update data

        Returns:
            Updated session data

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        response = await self.client.put(
            f"{self.request_manager_url}/api/v1/sessions/{session_id}",
            json=session_update,
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
        timeout: float = 180.0,
    ):
        """
        Initialize the CLI chat client.

        Args:
            request_manager_url: URL of the Request Manager service
            user_id: User ID for authentication (generates UUID if not provided)
            timeout: HTTP client timeout in seconds
        """
        super().__init__(request_manager_url, user_id, timeout)
        self.session_id: Optional[str] = None

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
            "cli_session_id": self.session_id,
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

            # Update session ID from response
            self.session_id = result.get("session_id", self.session_id)

            # Extract response content
            response_data = result.get("response", {})
            return response_data.get("content", "No response content")

        except httpx.HTTPError as e:
            return f"Error communicating with Request Manager: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def reset_session(self) -> bool:
        """
        Reset the current session.

        Returns:
            True if session was reset successfully, False otherwise
        """
        if self.session_id:
            try:
                await self.update_session(self.session_id, {"status": "INACTIVE"})
                self.session_id = None
                return True
            except Exception:
                return False
        return True

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
                elif message.lower() == "reset":
                    if await self.reset_session():
                        print("Session cleared. Starting fresh!")
                    else:
                        print("No active session to clear.")
                    continue

                if message.strip():
                    agent_response = await self.send_message(message, debug=debug)
                    print(f"agent: {agent_response}")

            except KeyboardInterrupt:
                break

        await self.close()
        print("\nbye!")
