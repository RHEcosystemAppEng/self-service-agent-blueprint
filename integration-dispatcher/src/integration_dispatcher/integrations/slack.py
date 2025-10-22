"""Slack integration handler."""

import os
from typing import Any, Dict

from shared_models import configure_logging
from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from .base import BaseIntegrationHandler, IntegrationResult

logger = configure_logging("integration-dispatcher")


class SlackIntegrationHandler(BaseIntegrationHandler):
    """Handler for Slack message delivery."""

    def __init__(self) -> None:
        super().__init__()
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.client = AsyncWebClient(token=self.bot_token) if self.bot_token else None

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """Deliver message to Slack."""
        if not self.client:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message="Slack bot token not configured",
            )

        try:
            slack_config = config.config

            logger.info(
                "Slack integration config received",
                user_id=request.user_id,
                config=slack_config,
            )

            # Determine target channel
            channel = slack_config.get("channel_id")
            if not channel:
                # Try to find user's DM channel using user_email
                user_email = slack_config.get("user_email")
                if user_email:
                    channel = await self._get_user_dm_channel(user_email)
                else:
                    # Try to use slack_user_id for DM channel
                    slack_user_id = slack_config.get("slack_user_id")
                    if slack_user_id:
                        channel = await self._get_user_dm_channel_by_id(slack_user_id)
                    else:
                        return IntegrationResult(
                            success=False,
                            status=DeliveryStatus.FAILED,
                            message="No channel_id, user_email, or slack_user_id configured",
                        )

            # Build message blocks
            blocks = self._build_message_blocks(
                template_content.get("body", ""),
                request,
                dict(slack_config) if slack_config else {},
            )

            # Send message
            response = await self.client.chat_postMessage(
                channel=channel,
                text=template_content.get("subject", "Agent Response"),
                blocks=blocks,
                thread_ts=(
                    slack_config.get("thread_ts")
                    if slack_config.get("thread_replies")
                    else None
                ),
            )

            if response["ok"]:
                return IntegrationResult(
                    success=True,
                    status=DeliveryStatus.DELIVERED,
                    message="Message delivered to Slack",
                    metadata={
                        "channel": response["channel"],
                        "ts": response["ts"],
                        "message_id": response.get("message", {}).get("ts"),  # type: ignore[call-overload]
                    },
                )
            else:
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message=f"Slack API error: {response.get('error', 'Unknown error')}",
                )

        except SlackApiError as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Slack API error: {e.response['error']}",
                retry_after=60 if e.response.get("error") == "rate_limited" else None,
            )
        except Exception as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Unexpected error: {str(e)}",
            )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Slack configuration."""
        # Must have either channel_id, user_email, or slack_user_id
        has_channel = bool(config.get("channel_id"))
        has_user_email = bool(config.get("user_email"))
        has_slack_user_id = bool(config.get("slack_user_id"))

        if not (has_channel or has_user_email or has_slack_user_id):
            return False

        # Validate channel_id format if provided
        if has_channel:
            channel_id = config["channel_id"]
            if not (
                channel_id.startswith("C")
                or channel_id.startswith("D")
                or channel_id.startswith("G")
            ):
                return False

        return True

    async def health_check(self) -> bool:
        """Check Slack API connectivity."""
        import structlog

        logger = structlog.get_logger()

        logger.debug(
            "Slack integration health check started",
            has_client=bool(self.client),
            has_bot_token=bool(self.bot_token),
        )

        if not self.client:
            logger.warning(
                "Slack integration health check failed - no client (missing bot token)"
            )
            return False

        try:
            logger.debug("Testing Slack API connectivity...")
            response = await self.client.auth_test()
            if response["ok"]:
                logger.debug(
                    "Slack integration health check passed",
                    user_id=response.get("user_id"),
                    team_id=response.get("team_id"),
                )
                return True
            else:
                logger.warning("Slack API auth test failed", response=response)
                return False
        except Exception as e:
            logger.error(
                "Slack integration health check failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def get_required_config_fields(self) -> list[str]:
        """Required Slack configuration fields."""
        return (
            []
        )  # Either channel_id, user_email, or slack_user_id is required, but not all

    def get_optional_config_fields(self) -> list[str]:
        """Optional Slack configuration fields."""
        return [
            "channel_id",
            "user_email",
            "slack_user_id",
            "workspace_id",
            "thread_replies",
            "mention_user",
            "include_agent_info",
            "thread_ts",
        ]

    async def _get_user_dm_channel(self, user_email: str) -> str:
        """Get or create DM channel with user."""
        if not self.client:
            raise Exception("Slack client not initialized")
        try:
            # Find user by email
            users_response = await self.client.users_lookupByEmail(email=user_email)
            if not users_response["ok"]:
                raise Exception(f"User not found: {user_email}")

            user_id = users_response["user"]["id"]

            # Open DM channel
            dm_response = await self.client.conversations_open(users=[user_id])
            if not dm_response["ok"]:
                raise Exception("Failed to open DM channel")

            channel_id = dm_response["channel"]["id"]
            return str(channel_id) if channel_id is not None else ""

        except Exception as e:
            raise Exception(f"Failed to get DM channel: {str(e)}")

    async def _get_user_dm_channel_by_id(self, user_id: str) -> str:
        """Get or create DM channel with user by user ID."""
        if not self.client:
            raise Exception("Slack client not initialized")
        try:
            # Open DM channel directly with user ID
            dm_response = await self.client.conversations_open(users=[user_id])
            if not dm_response["ok"]:
                raise Exception("Failed to open DM channel")

            channel_id = dm_response["channel"]["id"]
            return str(channel_id) if channel_id is not None else ""

        except Exception as e:
            raise Exception(f"Failed to get DM channel for user {user_id}: {str(e)}")

    def _build_message_blocks(
        self,
        content: str,
        request: DeliveryRequest,
        config: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        """Build Slack message blocks."""
        blocks: list[Dict[str, Any]] = []

        # Main content block
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": content,
                },
            }
        )

        # Agent info if enabled
        if config.get("include_agent_info") and request.agent_id:
            elements: list[Dict[str, str]] = [
                {
                    "type": "mrkdwn",
                    "text": f"_Response from agent: {request.agent_id}_",
                }
            ]
            blocks.append(
                {
                    "type": "context",
                    "elements": elements,
                }
            )

        # Only add buttons for final AI responses (not for acknowledgments/processing messages)
        if request.agent_id and not self._is_system_message(content):
            # Add divider
            blocks.append({"type": "divider"})

            # Action buttons
            buttons = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📋 View Session"},
                    "value": request.session_id,
                    "action_id": "view_session",
                    "style": "primary",
                }
            ]

            # Note: Removed "Ask Follow-up" button as it only showed instructions
            # Users already know how to continue with /agent or @mention

            # Add "Start New Session" button to allow fresh conversation context
            buttons.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🆕 Start New Session"},
                    "value": f"new_session:{request.session_id}",
                    "action_id": "new_session",
                }
            )

            blocks.append({"type": "actions", "elements": buttons})

        return blocks

    def _is_system_message(self, content: str) -> bool:
        """Check if this is a system message (acknowledgment/processing) vs AI response."""
        system_indicators = [
            "processing your request",
            "request has been received",
            "being processed",
            "✅",  # checkmark often indicates system message
        ]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in system_indicators)
