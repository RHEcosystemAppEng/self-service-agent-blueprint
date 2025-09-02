"""Slack service for handling events and interactions."""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import structlog
from cloudevents.http import CloudEvent, to_structured
from shared_clients import AgentServiceClient
from shared_clients.service_client import RequestManagerClient
from shared_models import CloudEventBuilder, EventTypes, verify_slack_signature

from .slack_schemas import SlackInteractionPayload, SlackSlashCommand

logger = structlog.get_logger()


class SlackService:
    """Service for handling Slack events and interactions."""

    def __init__(self):
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        self.request_manager_client = RequestManagerClient()
        self.agent_service_client = AgentServiceClient()
        # Simple rate limiting: track last request time per user
        self._last_request_time = {}
        # Eventing configuration
        self.eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"
        self.broker_url = os.getenv("BROKER_URL")

    def verify_slack_signature(
        self, body: bytes, timestamp: str, signature: str
    ) -> bool:
        """Verify Slack request signature using shared utility."""
        return verify_slack_signature(
            body=body,
            timestamp=timestamp,
            signature=signature,
            secret=self.signing_secret,
            debug_logging=True,  # Enable debug logging for this service
        )

    async def _send_cloudevent(
        self, event_data: Dict[str, Any], event_type: str
    ) -> bool:
        """Send a CloudEvent to the broker."""
        if not self.eventing_enabled or not self.broker_url:
            logger.info("Eventing disabled or no broker URL - skipping CloudEvent")
            return False

        try:
            # Create CloudEvent using shared utilities
            builder = CloudEventBuilder("integration-dispatcher")
            if event_type == EventTypes.REQUEST_CREATED:
                event = builder.create_request_event(
                    event_data,
                    event_data.get("request_id"),
                    event_data.get("user_id"),
                    event_data.get("session_id"),
                )
            else:
                # For other event types, create a basic event
                event = CloudEvent(
                    {
                        "type": event_type,
                        "source": "integration-dispatcher",
                        "id": str(uuid.uuid4()),
                        "time": datetime.now(timezone.utc).isoformat(),
                    },
                    event_data,
                )

            # Send to broker
            headers, body = to_structured(event)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.broker_url,
                    headers=headers,
                    content=body,
                    timeout=30.0,
                )
                response.raise_for_status()

            logger.info(
                "CloudEvent sent successfully",
                event_type=event_type,
                event_id=event["id"],
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to send CloudEvent",
                event_type=event_type,
                error=str(e),
            )
            return False

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
            # Provide default team_id if not available
            effective_team_id = team_id or "unknown"

            metadata = {
                "slack_channel": channel,
                "slack_thread_ts": thread_ts,
                "slack_team_id": effective_team_id,
                "source": "slack_message",
            }

            logger.debug(
                "Creating Slack metadata",
                user_id=user_id,
                channel=channel,
                thread_ts=thread_ts,
                team_id=team_id,
                effective_team_id=effective_team_id,
                metadata=metadata,
            )

            await self._forward_to_request_manager(
                user_id=user_id,
                content=text,
                integration_type="SLACK",
                metadata=metadata,
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
                integration_type="SLACK",
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
                            logger.debug(
                                "Session info response URL post completed",
                                status_code=response.status_code,
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
                    await self.agent_service_client.update_session(
                        old_session_id, {"status": "INACTIVE"}
                    )
                    logger.debug(
                        "Session closed successfully", session_id=old_session_id
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
                        integration_type="SLACK",
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
                                logger.debug(
                                    "Fallback new session response URL post completed",
                                    status_code=response.status_code,
                                )
                                response.raise_for_status()
                        except Exception as fallback_e:
                            logger.error(
                                "Failed to post fallback new session message",
                                error=str(fallback_e),
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
                    integration_type="SLACK",
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
        """Clean message text by removing bot mentions and extra whitespace."""
        import re

        # Remove <@BOTID> mentions (both user and workspace mentions)
        text = re.sub(r"<@[UW][A-Z0-9]+>", "", text)
        # Remove multiple consecutive whitespace characters
        text = re.sub(r"\s+", " ", text)
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

            # Create payload - Request Manager will generate request_id and session_id
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

            logger.debug(
                "Sending Slack request to Request Manager",
                user_id=user_id,
                channel_id=channel_id,
                slack_user_id=slack_user_id,
                slack_team_id=slack_team_id,
                thread_id=thread_id,
                payload=payload,
            )

            # Always use Request Manager HTTP API - it handles session management and eventing
            response = await self.request_manager_client.send_slack_request(payload)
            if response:
                logger.info(
                    "Request forwarded to Request Manager",
                    user_id=user_id,
                    status="success",
                )
            else:
                logger.error(
                    "Failed to forward request to Request Manager",
                    user_id=user_id,
                )

        except Exception as e:
            logger.error(
                "Failed to forward request to Request Manager",
                error=str(e),
                user_id=user_id,
            )
            raise

    async def _get_session_details(self, session_id: str) -> str:
        """Fetch session details from Agent Service."""
        try:
            session_data = await self.agent_service_client.get_session(session_id)
            if not session_data:
                return "Session not found"

            # Format session information
            created_at = session_data.get("created_at", "Unknown")
            if created_at != "Unknown":
                # Parse and format the datetime
                from datetime import datetime

                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    created_at = dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    pass

            total_requests = session_data.get("total_requests", 0)
            status = session_data.get("status", "Unknown")
            agent_id = session_data.get("current_agent_id", None) or "Not assigned"

            # Convert agent UUID to human-readable name using existing AgentMapping
            agent_name = agent_id
            if agent_id and agent_id != "Not assigned":
                try:
                    from shared_models import create_agent_mapping

                    agents_response = await self.agent_service_client.list_agents()
                    if agents_response and "agents" in agents_response:
                        # Create AgentMapping from the response
                        agent_mapping = create_agent_mapping(agents_response["agents"])
                        # Use the existing get_name method
                        agent_name = agent_mapping.get_name(agent_id) or agent_id
                except Exception as e:
                    logger.warning(
                        "Failed to convert agent UUID to name",
                        agent_id=agent_id,
                        error=str(e),
                    )

            return (
                f"📋 *Session Information*\n\n"
                f"**Session ID:** `{session_id}`\n"
                f"**Status:** {status}\n"
                f"**Created:** {created_at}\n"
                f"**Total Requests:** {total_requests}\n"
                f"**Current Agent:** {agent_name}\n\n"
                f"💡 **Continue this conversation by:**\n"
                f"• Using `/agent [your message]` in Slack\n"
                f"• Mentioning me in your message\n"
                f"• Sending a DM to this bot\n\n"
                f"Your session context will be maintained automatically!"
            )

        except Exception as e:
            logger.error(f"Error fetching session details: {e}")
            return f"Error fetching session details: {str(e)}"
