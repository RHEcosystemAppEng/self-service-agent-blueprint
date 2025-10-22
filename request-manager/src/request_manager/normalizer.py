"""Request normalization for different integration types."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from shared_models import get_enum_value
from shared_models.models import NormalizedRequest

from .schemas import BaseRequest, CLIRequest, SlackRequest, ToolRequest, WebRequest


class RequestNormalizer:
    """Normalizes requests from different integration types."""

    def normalize_request(
        self,
        request: Union[BaseRequest, SlackRequest, WebRequest, CLIRequest, ToolRequest],
        session_id: str,
        current_agent_id: Optional[str] = None,
    ) -> NormalizedRequest:
        """Normalize a request to the internal format."""
        request_id = str(uuid.uuid4())

        # Always start with target_agent_id as None to allow routing detection to work
        # The routing logic will determine the correct agent based on the conversation
        target_agent_id = None

        # Extract common fields
        base_data = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": request.user_id,
            "integration_type": request.integration_type,
            "request_type": request.request_type,
            "content": request.content,
            "created_at": datetime.now(timezone.utc),
            "target_agent_id": target_agent_id,
        }

        # Handle integration-specific normalization
        if isinstance(request, SlackRequest):
            return self._normalize_slack_request(request, base_data)
        elif isinstance(request, WebRequest):
            return self._normalize_web_request(request, base_data)
        elif isinstance(request, CLIRequest):
            return self._normalize_cli_request(request, base_data)
        elif isinstance(request, ToolRequest):
            return self._normalize_tool_request(request, base_data)
        else:
            return self._normalize_base_request(request, base_data)

    def _normalize_slack_request(
        self, request: SlackRequest, base_data: Dict[str, Any]
    ) -> NormalizedRequest:
        """Normalize Slack-specific request."""
        integration_context = {
            "channel_id": request.channel_id,
            "thread_id": request.thread_id,
            "slack_user_id": request.slack_user_id,
            "slack_team_id": request.slack_team_id,
            "platform": "slack",
        }

        # Extract user context from Slack metadata
        user_context = self._extract_slack_user_context(request)

        return NormalizedRequest(
            **base_data,
            integration_context=integration_context,
            user_context=user_context,
            requires_routing=True,
        )

    def _normalize_web_request(
        self, request: WebRequest, base_data: Dict[str, Any]
    ) -> NormalizedRequest:
        """Normalize web interface request."""
        integration_context = {
            "session_token": request.session_token,
            "client_ip": request.client_ip,
            "user_agent": request.user_agent,
            "platform": "web",
        }

        user_context = self._extract_web_user_context(request)

        return NormalizedRequest(
            **base_data,
            integration_context=integration_context,
            user_context=user_context,
            requires_routing=True,
        )

    def _normalize_cli_request(
        self, request: CLIRequest, base_data: Dict[str, Any]
    ) -> NormalizedRequest:
        """Normalize CLI request."""
        integration_context = {
            "cli_session_id": request.cli_session_id,
            "command_context": request.command_context,
            "platform": "cli",
        }

        user_context = self._extract_cli_user_context(request)

        return NormalizedRequest(
            **base_data,
            integration_context=integration_context,
            user_context=user_context,
            requires_routing=True,
        )

    def _normalize_tool_request(
        self, request: ToolRequest, base_data: Dict[str, Any]
    ) -> NormalizedRequest:
        """Normalize tool-generated request."""
        integration_context = {
            "tool_id": request.tool_id,
            "tool_instance_id": request.tool_instance_id,
            "trigger_event": request.trigger_event,
            "tool_context": request.tool_context,
            "platform": "tool",
        }

        user_context = self._extract_tool_user_context(request)

        # Tool requests often target specific agents or don't need routing
        target_agent = self._extract_target_agent_from_tool(request)

        # Override default if tool specifies a specific agent
        if target_agent is not None:
            base_data["target_agent_id"] = target_agent

        return NormalizedRequest(
            **base_data,
            integration_context=integration_context,
            user_context=user_context,
            requires_routing=target_agent is None,
        )

    def _normalize_base_request(
        self, request: BaseRequest, base_data: Dict[str, Any]
    ) -> NormalizedRequest:
        """Normalize basic request."""
        # Handle both enum and string cases defensively
        platform_value = get_enum_value(request.integration_type)
        integration_context = {
            "platform": platform_value,
            "metadata": request.metadata,
        }

        return NormalizedRequest(
            **base_data,
            integration_context=integration_context,
            user_context={},
            requires_routing=True,
        )

    def _extract_slack_user_context(self, request: SlackRequest) -> Dict[str, Any]:
        """Extract user context from Slack request."""
        # Determine channel type - if channel_id is None, it's a DM request
        if request.channel_id is None:
            channel_type = "dm"
        elif request.channel_id.startswith("D"):
            channel_type = "dm"
        else:
            channel_type = "channel"

        context = {
            "platform_user_id": request.slack_user_id,
            "team_id": request.slack_team_id,
            "channel_type": channel_type,
        }

        # Add any additional context from metadata
        if request.metadata:
            context.update(request.metadata)

        return context

    def _extract_web_user_context(self, request: WebRequest) -> Dict[str, Any]:
        """Extract user context from web request."""
        context = {
            "client_ip": request.client_ip,
            "user_agent": request.user_agent,
            "has_session": request.session_token is not None,
        }

        # Parse user agent for additional context
        if request.user_agent:
            context.update(self._parse_user_agent(request.user_agent))

        if request.metadata:
            context.update(request.metadata)

        return context

    def _extract_cli_user_context(self, request: CLIRequest) -> Dict[str, Any]:
        """Extract user context from CLI request."""
        context = {
            "cli_session": request.cli_session_id,
            "command_context": request.command_context,
        }

        if request.metadata:
            context.update(request.metadata)

        return context

    def _extract_tool_user_context(self, request: ToolRequest) -> Dict[str, Any]:
        """Extract user context from tool request."""
        context = {
            "originating_tool": request.tool_id,
            "tool_instance": request.tool_instance_id,
            "trigger_event": request.trigger_event,
            "automated_request": True,
        }

        # Merge tool context
        if request.tool_context:
            context.update(request.tool_context)

        if request.metadata:
            context.update(request.metadata)

        return context

    def _extract_target_agent_from_tool(self, request: ToolRequest) -> str | None:
        """Extract target agent ID from tool request if specified."""
        # Check if tool context specifies a target agent
        if request.tool_context and "target_agent_id" in request.tool_context:
            agent_id = request.tool_context["target_agent_id"]
            return str(agent_id) if agent_id is not None else None

        # Check metadata for agent specification
        if request.metadata and "target_agent_id" in request.metadata:
            agent_id = request.metadata["target_agent_id"]
            return str(agent_id) if agent_id is not None else None

        # Tool-specific routing logic could go here
        # For example, certain tools might always route to specific agents
        tool_agent_mapping = {
            "snow-integration": "laptop-refresh-agent",
            "email-service": "email-change-agent",
            "hr-system": "routing-agent",
        }

        return tool_agent_mapping.get(request.tool_id)

    def _parse_user_agent(self, user_agent: str) -> Dict[str, Any]:
        """Parse user agent string for browser/OS information."""
        # Simple user agent parsing - could be enhanced with a proper library
        context: Dict[str, Any] = {"raw_user_agent": user_agent}

        user_agent_lower = user_agent.lower()

        # Browser detection
        if "chrome" in user_agent_lower:
            context["browser"] = "chrome"
        elif "firefox" in user_agent_lower:
            context["browser"] = "firefox"
        elif "safari" in user_agent_lower:
            context["browser"] = "safari"
        elif "edge" in user_agent_lower:
            context["browser"] = "edge"

        # OS detection (order matters - check iOS before macOS)
        if "windows" in user_agent_lower:
            context["os"] = "windows"
        elif (
            "iphone" in user_agent_lower
            or "ipad" in user_agent_lower
            or "ios" in user_agent_lower
        ):
            context["os"] = "ios"
        elif "android" in user_agent_lower:
            context["os"] = "android"
        elif "mac os" in user_agent_lower or "macos" in user_agent_lower:
            context["os"] = "macos"
        elif "linux" in user_agent_lower:
            context["os"] = "linux"

        # Mobile detection
        mobile_indicators = ["mobile", "android", "iphone", "ipad"]
        context["is_mobile"] = any(
            indicator in user_agent_lower for indicator in mobile_indicators
        )

        return context
