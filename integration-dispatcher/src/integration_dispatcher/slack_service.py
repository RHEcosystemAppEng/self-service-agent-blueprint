"""Slack service for handling events and interactions."""

import hashlib
import hmac
import os
import time
from typing import Dict, Optional

import httpx
import structlog

from .slack_schemas import SlackInteractionPayload, SlackSlashCommand

logger = structlog.get_logger()


class SlackService:
    """Service for handling Slack events and interactions."""

    def __init__(self):
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        self.request_manager_url = os.getenv(
            "REQUEST_MANAGER_URL", "http://self-service-agent-request-manager"
        )
        # Simple rate limiting: track last request time per user
        self._last_request_time = {}

    def verify_slack_signature(
        self, body: bytes, timestamp: str, signature: str
    ) -> bool:
        """Verify Slack request signature."""
        print(
            f"DEBUG: verify_slack_signature called, timestamp={timestamp}, signature={signature[:20] + '...' if signature else 'None'}"
        )
        if not self.signing_secret:
            print("WARNING: Slack signing secret not configured, skipping verification")
            return True

        # Check timestamp to prevent replay attacks
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:  # 5 minutes
            logger.warning("Slack request timestamp too old", timestamp=timestamp)
            return False

        # Create signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_signature = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
            ).hexdigest()
        )

        return hmac.compare_digest(expected_signature, signature)

    async def handle_message_event(self, event: Dict, team_id: str = None) -> None:
        """Handle incoming Slack message."""
        try:
            # Log all message events for debugging
            logger.info(
                "Message event received",
                event_type=event.get("type"),
                subtype=event.get("subtype"),
                bot_id=event.get("bot_id"),
                app_id=event.get("app_id"),
                user_id=event.get("user"),
                text_preview=event.get("text", "")[:100] if event.get("text") else None,
                channel=event.get("channel"),
                ts=event.get("ts"),
            )

            # Enhanced bot message filtering to prevent infinite loops
            if (
                event.get("bot_id")
                or event.get("subtype") == "bot_message"
                or event.get("subtype") == "message_changed"
                or event.get("subtype") == "message_deleted"
                or event.get("subtype") == "message_replied"  # Add this
                or event.get("app_id")  # Messages from apps (including our own)
                or not event.get("user")  # Messages without a user (system messages)
            ):
                logger.info(
                    "Skipping bot/system message to prevent loops",
                    bot_id=event.get("bot_id"),
                    subtype=event.get("subtype"),
                    app_id=event.get("app_id"),
                    has_user=bool(event.get("user")),
                )
                return

            user_id = event.get("user")
            text = event.get("text", "").strip()
            channel = event.get("channel")
            thread_ts = event.get("thread_ts") or event.get("ts")

            if not text or not user_id:
                return

            # Skip messages that look like session information or system messages (to prevent loops)
            session_indicators = [
                "Session Information",
                "Session ID:",
                "Continue this conversation by:",
                "**Session ID:**",
                "**Status:**",
                "**Created:**",
                "**Total Requests:**",
                "**Current Agent:**",
                "Your session context will be maintained",
            ]

            if text.startswith("📋") or any(
                indicator in text for indicator in session_indicators
            ):
                logger.debug(
                    "Skipping session information message to prevent loops",
                    text_preview=text[:50],
                )
                return

            # Remove bot mentions from text
            text = self._clean_message_text(text)

            # Simple rate limiting to prevent rapid-fire requests
            import time

            current_time = time.time()
            last_request_time = self._last_request_time.get(user_id, 0)

            if current_time - last_request_time < 2.0:  # 2 second cooldown
                logger.debug(
                    "Rate limiting: ignoring rapid request",
                    user_id=user_id,
                    time_since_last=current_time - last_request_time,
                )
                return

            self._last_request_time[user_id] = current_time

            logger.info(
                "Processing Slack message",
                user_id=user_id,
                channel=channel,
                text=text[:100],  # Log first 100 chars
            )

            # Forward to Request Manager
            await self._forward_to_request_manager(
                user_id=user_id,
                content=text,
                integration_type="slack",
                metadata={
                    "slack_channel": channel,
                    "slack_thread_ts": thread_ts,
                    "slack_team_id": team_id,
                    "source": "slack_message",
                },
            )

        except Exception as e:
            logger.error("Error handling Slack message", error=str(e), event=event)

    async def handle_slash_command(self, command: SlackSlashCommand) -> Dict:
        """Handle Slack slash command."""
        try:
            if not command.text.strip():
                return {
                    "response_type": "ephemeral",
                    "text": "👋 Hi! Please include your request after the command.\n"
                    "Example: `/agent I need help with my laptop refresh`",
                }

            logger.info(
                "Processing Slack slash command",
                user_id=command.user_id,
                command=command.command,
                text=command.text[:100],
            )

            # Forward to Request Manager
            await self._forward_to_request_manager(
                user_id=command.user_id,
                content=command.text,
                integration_type="slack",
                metadata={
                    "slack_channel": command.channel_id,
                    "slack_response_url": command.response_url,
                    "slack_team_id": command.team_id,
                    "source": "slash_command",
                },
            )

            return {
                "response_type": "ephemeral",
                "text": "🚀 Your request has been submitted! I'll send you a response shortly.",
            }

        except Exception as e:
            logger.error(
                "Error handling slash command", error=str(e), command=command.dict()
            )
            return {
                "response_type": "ephemeral",
                "text": "❌ Sorry, there was an error processing your request. Please try again.",
            }

    async def handle_button_interaction(self, payload: SlackInteractionPayload) -> Dict:
        """Handle button interactions."""
        try:
            logger.info(
                "Button interaction received",
                user_id=payload.user.id,
                actions=payload.actions,
                payload_type=payload.type,
            )

            if not payload.actions:
                logger.warning("No actions in button interaction")
                return {"text": "No action specified"}

            action = payload.actions[0]
            action_id = action.get("action_id")
            action_value = action.get("value", "")

            logger.info(
                "Processing button action",
                action_id=action_id,
                action_value=action_value,
            )

            if action_id == "view_session":
                session_id = action_value

                # Fetch session details from Request Manager
                session_details = await self._get_session_details(session_id)

                # Use response_url to post the session information
                if payload.response_url:
                    session_info_message = {
                        "replace_original": False,  # Keep original message, add new ephemeral one
                        "response_type": "ephemeral",
                        "text": session_details,
                    }

                    # Post to response URL
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                payload.response_url,
                                json=session_info_message,
                                timeout=10.0,
                            )
                            print(
                                f"DEBUG: Session info response URL post status: {response.status_code}"
                            )
                            response.raise_for_status()
                    except Exception as e:
                        logger.error(f"Failed to post session info: {e}")

                return {"text": "Session info sent!"}

            elif action_id == "new_session":
                # Handle starting a new session
                old_session_id = action_value.replace("new_session:", "")

                # Close the current session by marking it as completed
                try:
                    async with httpx.AsyncClient() as client:
                        close_response = await client.put(
                            f"{self.request_manager_url}/api/v1/sessions/{old_session_id}",
                            json={"status": "INACTIVE"},
                            timeout=10.0,
                        )
                        print(
                            f"DEBUG: Session close status: {close_response.status_code}"
                        )
                        if close_response.status_code != 200:
                            print(
                                f"DEBUG: Failed to close session: {close_response.text}"
                            )
                except Exception as e:
                    logger.error(f"Error closing session: {e}")

                # Create a new session and immediately send a message to routing-agent
                try:
                    # Extract user info from the payload
                    user_id = payload.user.id
                    channel_id = payload.channel.id if payload.channel else None
                    team_id = payload.team.id if payload.team else None

                    # Create a new session by sending a message to the routing-agent
                    new_session_content = "Hello! I'd like to start a fresh conversation. Please introduce yourself and tell me how you can help."

                    # Forward to Request Manager to create new session and route to routing-agent
                    await self._forward_to_request_manager(
                        user_id=user_id,
                        content=new_session_content,
                        integration_type="slack",
                        metadata={
                            "slack_channel": channel_id,
                            "slack_team_id": team_id,
                            "source": "new_session_button",
                            "previous_session_id": old_session_id,
                        },
                    )

                    logger.info(f"Successfully created new session for user {user_id}")

                except Exception as e:
                    logger.error(f"Error creating new session: {e}")
                    # Fallback to the old behavior if new session creation fails
                    if payload.response_url:
                        fallback_message = {
                            "replace_original": True,
                            "text": f"🆕 *Starting New Session*\n\n"
                            f"Previous session: `{old_session_id}`\n\n"
                            f"Your next message will start a fresh conversation with no previous context.\n\n"
                            f"To continue with a new topic, simply:\n"
                            f"• Use `/agent [your new question]`\n"
                            f"• Send me a direct message\n"
                            f"• Mention me in a channel\n\n"
                            f"The system will automatically create a new session for your next interaction!",
                        }

                        try:
                            async with httpx.AsyncClient() as client:
                                response = await client.post(
                                    payload.response_url,
                                    json=fallback_message,
                                    timeout=10.0,
                                )
                                print(
                                    f"DEBUG: Fallback new session response URL post status: {response.status_code}"
                                )
                                response.raise_for_status()
                        except Exception as fallback_e:
                            print(
                                f"DEBUG: Failed to post fallback new session message: {fallback_e}"
                            )

                return {"text": "Starting new session..."}

            return {"text": "Unknown action"}

        except Exception as e:
            logger.error("Error handling button interaction", error=str(e))
            return {"text": "❌ Error processing interaction"}

    async def handle_modal_submission(self, payload: SlackInteractionPayload) -> Dict:
        """Handle modal form submissions."""
        try:
            callback_id = payload.view.get("callback_id", "")

            if callback_id.startswith("followup_modal:"):
                session_id = callback_id.replace("followup_modal:", "")

                # Extract the user's input from the modal
                values = payload.view.get("state", {}).get("values", {})
                followup_input = (
                    values.get("followup_input_block", {})
                    .get("followup_input", {})
                    .get("value", "")
                )

                if not followup_input.strip():
                    return {
                        "response_action": "errors",
                        "errors": {
                            "followup_input_block": "Please enter your follow-up question"
                        },
                    }

                logger.info(
                    "Processing follow-up from modal",
                    user_id=payload.user.id,
                    session_id=session_id,
                    text=followup_input[:100],
                )

                # Forward to Request Manager with session context
                await self._forward_to_request_manager(
                    user_id=payload.user.id,
                    content=followup_input,
                    integration_type="slack",
                    metadata={
                        "slack_channel": (
                            payload.channel.id if payload.channel else payload.user.id
                        ),
                        "source": "slack_followup_modal",
                        "session_id": session_id,  # Include session ID for continuity
                    },
                )

                return {"response_action": "clear"}

            return {"response_action": "clear"}

        except Exception as e:
            logger.error("Error handling modal submission", error=str(e))
            return {
                "response_action": "errors",
                "errors": {
                    "followup_input_block": "Sorry, there was an error processing your request. Please try again."
                },
            }

    def _clean_message_text(self, text: str) -> str:
        """Clean message text by removing bot mentions."""
        import re

        # Remove <@BOTID> mentions
        text = re.sub(r"<@[UW][A-Z0-9]+>", "", text)
        # Remove extra whitespace
        return text.strip()

    async def _forward_to_request_manager(
        self,
        user_id: str,
        content: str,
        integration_type: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Forward request to Request Manager."""
        try:
            # Extract Slack-specific fields from metadata
            channel_id = metadata.get("slack_channel", "") if metadata else ""
            thread_id = metadata.get("slack_thread_ts") if metadata else None
            slack_user_id = user_id  # Slack user ID is the same as user_id
            slack_team_id = metadata.get("slack_team_id", "") if metadata else ""

            payload = {
                "user_id": user_id,
                "content": content,
                "integration_type": integration_type,
                "request_type": "slack_interaction",
                "channel_id": channel_id,
                "thread_id": thread_id,
                "slack_user_id": slack_user_id,
                "slack_team_id": slack_team_id,
                "metadata": metadata or {},
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.request_manager_url}/api/v1/requests/slack",
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()

                logger.info(
                    "Request forwarded to Request Manager",
                    user_id=user_id,
                    status_code=response.status_code,
                )

        except Exception as e:
            logger.error(
                "Failed to forward request to Request Manager",
                error=str(e),
                user_id=user_id,
            )
            raise

    async def _get_session_details(self, session_id: str) -> str:
        """Fetch session details from Request Manager."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.request_manager_url}/api/v1/sessions/{session_id}",
                    timeout=10.0,
                )

                if response.status_code == 200:
                    session_data = response.json()

                    # Format session information
                    created_at = session_data.get("created_at", "Unknown")
                    if created_at != "Unknown":
                        # Parse and format the datetime
                        from datetime import datetime

                        try:
                            dt = datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            )
                            created_at = dt.strftime("%Y-%m-%d %H:%M UTC")
                        except Exception:
                            pass

                    total_requests = session_data.get("total_requests", 0)
                    status = session_data.get("status", "Unknown")
                    agent_id = session_data.get("current_agent_id") or "Not assigned"

                    return (
                        f"📋 *Session Information*\n\n"
                        f"**Session ID:** `{session_id}`\n"
                        f"**Status:** {status}\n"
                        f"**Created:** {created_at}\n"
                        f"**Total Requests:** {total_requests}\n"
                        f"**Current Agent:** {agent_id}\n\n"
                        f"💡 **Continue this conversation by:**\n"
                        f"• Using `/agent [your message]` in Slack\n"
                        f"• Mentioning me in your message\n"
                        f"• Sending a DM to this bot\n\n"
                        f"Your session context will be maintained automatically!"
                    )
                else:
                    return (
                        f"📋 *Session Information*\n\n"
                        f"**Session ID:** `{session_id}`\n"
                        f"**Status:** Unable to fetch details (HTTP {response.status_code})\n\n"
                        f"💡 **Continue this conversation by:**\n"
                        f"• Using `/agent [your message]` in Slack\n"
                        f"• Mentioning me in your message\n"
                        f"• Sending a DM to this bot"
                    )

        except Exception as e:
            logger.error(
                "Failed to fetch session details", session_id=session_id, error=str(e)
            )
            return (
                f"📋 *Session Information*\n\n"
                f"**Session ID:** `{session_id}`\n"
                f"**Status:** Unable to fetch details (error: {str(e)})\n\n"
                f"💡 **Continue this conversation by:**\n"
                f"• Using `/agent [your message]` in Slack\n"
                f"• Mentioning me in your message\n"
                f"• Sending a DM to this bot"
            )
