"""Slack service for handling events and interactions."""

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from cloudevents.http import CloudEvent, to_structured
from shared_clients import AgentServiceClient
from shared_clients.service_client import RequestManagerClient
from shared_clients.stream_processor import LlamaStackStreamProcessor
from shared_models import (
    CloudEventBuilder,
    EventTypes,
    configure_logging,
    verify_slack_signature,
)
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from .slack_schemas import SlackInteractionPayload, SlackSlashCommand

logger = configure_logging("integration-dispatcher")


class SlackService:
    """Service for handling Slack events and interactions."""

    def __init__(self) -> None:
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET")
        self.request_manager_client = RequestManagerClient(
            timeout=60.0
        )  # Reduced from 180s
        self.agent_service_client = AgentServiceClient()
        # Simple rate limiting: track last request time per user
        self._last_request_time: Dict[str, float] = {}
        # Eventing configuration
        self.eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"
        self.broker_url = os.getenv("BROKER_URL")
        # Slack client for API calls
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.slack_client = (
            AsyncWebClient(token=self.bot_token) if self.bot_token else None
        )

    def _create_slack_message_id(
        self, event: Dict[str, Any], event_id: str | None = None
    ) -> str:
        """Create a unique identifier for a Slack message using Slack's event_id."""
        if event_id:
            # Use Slack's event_id which is globally unique and designed for deduplication
            return f"slack-event-{event_id}"
        else:
            # Fallback to timestamp-based approach if event_id not available
            user_id = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")
            return f"slack-{channel}-{user_id}-{ts}"

    def verify_slack_signature(
        self, body: bytes, timestamp: str, signature: str
    ) -> bool:
        """Verify Slack request signature using shared utility."""
        if self.signing_secret is None:
            logger.warning("Slack signing secret not configured, skipping verification")
            return True  # Skip verification if not configured

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
                    timeout=15.0,  # Reduced from 30s for faster failure detection
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

    async def handle_message_event(
        self,
        event: Dict[str, Any],
        team_id: str | None = None,
        db_session: Any = None,
        event_id: str | None = None,
    ) -> None:
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

            # ✅ SLACK MESSAGE DEDUPLICATION: Check if this Slack message was already processed
            logger.info(
                "Starting Slack message deduplication check",
                has_db_session=bool(db_session),
                has_ts=bool(event.get("ts")),
                channel=event.get("channel"),
                ts=event.get("ts"),
            )

            if db_session and event.get("ts"):
                from shared_models.models import ProcessedEvent
                from sqlalchemy import select

                # Create a unique identifier for this Slack message
                # Use Slack's event_id for optimal deduplication
                slack_message_id = self._create_slack_message_id(event, event_id)

                logger.info(
                    "Checking for duplicate Slack message",
                    slack_message_id=slack_message_id,
                    has_db_session=bool(db_session),
                    channel=event.get("channel"),
                    ts=event.get("ts"),
                )

                existing_message = await db_session.execute(
                    select(ProcessedEvent).where(
                        ProcessedEvent.event_id == slack_message_id
                    )
                )
                if existing_message.scalar_one_or_none():
                    logger.info(
                        "Slack message already processed - skipping duplicate",
                        slack_message_id=slack_message_id,
                        channel=event.get("channel"),
                        ts=event.get("ts"),
                        user_id=event.get("user"),
                    )
                    return

                # ✅ RECORD IMMEDIATELY: Record the message as processed to prevent race conditions
                try:
                    from shared_models.models import ProcessedEvent

                    processed_event = ProcessedEvent(
                        event_id=slack_message_id,
                        event_type="slack_message",
                        event_source="slack",
                        request_id=None,  # Will be set by request-manager
                        session_id=None,  # Will be set by request-manager
                        processed_by="integration-dispatcher",
                        processing_result="processing",
                        error_message=None,
                    )

                    db_session.add(processed_event)
                    await db_session.commit()

                    logger.info(
                        "Recorded Slack message as processing to prevent race conditions",
                        slack_message_id=slack_message_id,
                        channel=event.get("channel"),
                        ts=event.get("ts"),
                    )

                except Exception as e:
                    # Handle unique constraint violations gracefully (message already recorded)
                    if "duplicate key value violates unique constraint" in str(e):
                        logger.info(
                            "Slack message already recorded - skipping duplicate",
                            slack_message_id=slack_message_id,
                        )
                        return
                    else:
                        logger.error(
                            "Failed to record Slack message for deduplication",
                            slack_message_id=slack_message_id,
                            error=str(e),
                        )
                        await db_session.rollback()
                        # Continue processing even if recording fails
            else:
                logger.warning(
                    "Skipping Slack message deduplication - missing db_session or ts",
                    has_db_session=bool(db_session),
                    has_ts=bool(event.get("ts")),
                    channel=event.get("channel"),
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

            slack_user_id = event.get("user")
            text = event.get("text", "").strip()
            channel = event.get("channel")
            thread_ts = event.get("thread_ts") or event.get("ts")

            if not text or not slack_user_id:
                return

            # Resolve user ID (email or fallback to Slack user ID)
            user_id, original_slack_user_id = await self._resolve_user_id(
                slack_user_id, "message"
            )

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
                "slack_user_id": original_slack_user_id,  # Keep original Slack user ID for reference
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

            # ✅ MESSAGE ALREADY RECORDED: The deduplication record was created earlier to prevent race conditions

        except Exception as e:
            logger.error("Error handling Slack message", error=str(e), event=event)

    async def handle_slash_command(self, command: SlackSlashCommand) -> Dict[str, Any]:
        """Handle Slack slash command."""
        try:
            if not command.text.strip():
                return {
                    "response_type": "ephemeral",
                    "text": "👋 Hi! Please include your request after the command.\n"
                    "Example: `/agent I need help with my laptop refresh`",
                }

            # Send immediate acknowledgment to prevent timeout
            immediate_response = {
                "response_type": "ephemeral",
                "text": "🚀 Processing your request... I'll send you a response shortly.",
            }

            # Process the request asynchronously (don't await)
            asyncio.create_task(self._process_slash_command_async(command))

            return immediate_response

        except Exception as e:
            logger.error(
                "Error handling slash command", error=str(e), command=command.dict()
            )
            return {
                "response_type": "ephemeral",
                "text": "❌ Sorry, there was an error processing your request. Please try again.",
            }

    async def _process_slash_command_async(self, command: SlackSlashCommand) -> None:
        """Process slash command asynchronously and send response via DM."""
        try:
            # Resolve user ID (email or fallback to Slack user ID)
            user_id, original_slack_user_id = await self._resolve_user_id(
                command.user_id, "slash command"
            )

            # Forward to Request Manager
            await self._forward_to_request_manager(
                user_id=user_id,
                content=command.text,
                integration_type="SLACK",
                metadata={
                    "slack_channel": None,  # Don't use original channel for /agent commands - create DM instead
                    "slack_response_url": command.response_url,
                    "slack_team_id": command.team_id,
                    "slack_user_id": original_slack_user_id,  # Keep original Slack user ID for reference
                    "source": "slash_command",
                },
            )

        except Exception as e:
            logger.error(
                "Error processing slash command asynchronously",
                error=str(e),
                command=command.dict(),
            )

    async def handle_button_interaction(
        self, payload: SlackInteractionPayload
    ) -> Dict[str, Any]:
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
                                timeout=5.0,  # Reduced from 10s for faster failure detection
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
                    slack_user_id = payload.user["id"]  # type: ignore[index]
                    channel_id = payload.channel["id"] if payload.channel else None  # type: ignore[index]
                    team_id = payload.team["id"] if payload.team else None

                    # Resolve user ID (email or fallback to Slack user ID)
                    user_id, original_slack_user_id = await self._resolve_user_id(
                        slack_user_id, "button interaction"
                    )

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
                                    timeout=5.0,  # Reduced from 10s for faster failure detection
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

    async def handle_modal_submission(
        self, payload: SlackInteractionPayload
    ) -> Dict[str, Any]:
        """Handle modal form submissions."""
        try:
            if payload.view is None:
                logger.error("Modal payload missing view data")
                return {"text": "❌ Error processing modal submission"}

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

                # Resolve user ID (email or fallback to Slack user ID)
                slack_user_id = payload.user.id
                user_id, original_slack_user_id = await self._resolve_user_id(
                    slack_user_id, "modal submission"
                )

                logger.info(
                    "Processing follow-up from modal",
                    user_id=user_id,
                    session_id=session_id,
                    text=followup_input[:100],
                )

                # Forward to Request Manager with session context
                await self._forward_to_request_manager(
                    user_id=user_id,
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

    async def _get_user_email(self, slack_user_id: str) -> Optional[str]:
        """Fetch user email address from Slack API."""
        if not self.slack_client:
            logger.warning("Slack client not available - cannot fetch user email")
            return None

        try:
            response = await self.slack_client.users_info(user=slack_user_id)
            if response["ok"]:
                user_info = response["user"]
                email = user_info.get("profile", {}).get("email")
                if email:
                    logger.info(
                        "Successfully fetched user email from Slack",
                        slack_user_id=slack_user_id,
                        email=email,
                    )
                    return str(email) if email is not None else None
                else:
                    logger.warning(
                        "User email not found in Slack profile",
                        slack_user_id=slack_user_id,
                        user_info=user_info,
                    )
            else:
                logger.error(
                    "Failed to fetch user info from Slack",
                    slack_user_id=slack_user_id,
                    error=response.get("error"),
                )
        except SlackApiError as e:
            logger.error(
                "Slack API error fetching user info",
                slack_user_id=slack_user_id,
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "Unexpected error fetching user info",
                slack_user_id=slack_user_id,
                error=str(e),
            )

        return None

    async def _get_cached_email_from_slack_user_id(
        self, slack_user_id: str
    ) -> Optional[str]:
        """Get email from Slack user ID using cached mapping with TTL validation."""
        try:
            from shared_models.database import get_database_manager
            from shared_models.models import IntegrationType, UserIntegrationMapping
            from sqlalchemy import select

            db_manager = get_database_manager()
            async with db_manager.get_session() as db:
                # Find mapping by Slack user ID
                stmt = select(UserIntegrationMapping).where(
                    UserIntegrationMapping.integration_user_id == slack_user_id,
                    UserIntegrationMapping.integration_type == IntegrationType.SLACK,
                )
                result = await db.execute(stmt)
                mapping = result.scalar_one_or_none()

                if not mapping:
                    logger.debug(
                        "No cached mapping found for Slack user ID",
                        slack_user_id=slack_user_id,
                    )
                    return None

                # Use shared TTL validation logic
                from .integrations.defaults import IntegrationDefaultsService

                integration_defaults_service = IntegrationDefaultsService()

                is_valid = (
                    await integration_defaults_service._validate_mapping_with_ttl(
                        mapping, "slack user lookup"
                    )
                )

                if is_valid:
                    await db.commit()
                    return str(mapping.user_email)
                else:
                    await db.commit()
                    return None

        except Exception as e:
            logger.error(
                "Error getting cached email from Slack user ID",
                slack_user_id=slack_user_id,
                error=str(e),
            )
            return None

    async def _resolve_user_id(
        self, slack_user_id: str, context: str = "request"
    ) -> tuple[str, str]:
        """
        Resolve user ID by checking cache first, then fetching email from Slack API if needed.

        Returns:
            tuple: (resolved_user_id, slack_user_id) where resolved_user_id is either email or slack_user_id
        """
        logger.info(
            f"Resolving user ID for {context}",
            slack_user_id=slack_user_id,
        )

        # First, try to find existing mapping by Slack user ID (simple cache lookup)
        existing_email = await self._get_cached_email_from_slack_user_id(slack_user_id)
        if existing_email:
            logger.info(
                f"Using cached email for {context}",
                slack_user_id=slack_user_id,
                user_email=existing_email,
            )
            return existing_email, slack_user_id

        # If no cached mapping, fetch fresh from Slack API
        user_email = await self._get_user_email(slack_user_id)
        if user_email:
            logger.info(
                f"Using fresh email from Slack API for {context}",
                slack_user_id=slack_user_id,
                user_email=user_email,
            )
            # Store the mapping for future use
            from .user_mapping_utils import store_slack_user_mapping

            await store_slack_user_mapping(user_email, slack_user_id, "slack_service")
            return user_email, slack_user_id
        else:
            logger.warning(
                f"Could not fetch user email for {context}, using Slack user ID as fallback",
                slack_user_id=slack_user_id,
            )
            return slack_user_id, slack_user_id

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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Forward request to Request Manager."""
        try:
            # Extract Slack-specific fields from metadata
            if metadata is None:
                metadata = {}

            channel_id = metadata.get("slack_channel", "")
            thread_id = metadata.get("slack_thread_ts")
            slack_user_id = metadata.get("slack_user_id", user_id)
            slack_team_id = metadata.get("slack_team_id", "")

            logger.info(
                "Extracting Slack fields from metadata",
                user_id=user_id,
                metadata=metadata,
                slack_user_id=slack_user_id,
                channel_id=channel_id,
                thread_id=thread_id,
                slack_team_id=slack_team_id,
            )

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
            agent_name = session_data.get("current_agent_id", None) or "Not assigned"

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

    async def stream_slack_message(
        self, channel: str, content: str, thread_ts: Optional[str] = None
    ) -> bool:
        """Stream a message to Slack using optimized streaming."""
        try:
            # Use optimized streaming configuration
            config = LlamaStackStreamProcessor.get_optimal_stream_config(len(content))
            chunk_size = config["chunk_size"]

            # Send in optimized chunks for better user experience
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]

                # Send chunk to Slack
                await self._send_cloudevent(
                    {
                        "channel": channel,
                        "text": chunk,
                        "thread_ts": thread_ts,
                    },
                    "slack.message.stream",
                )

                # Small delay between chunks for better UX
                await asyncio.sleep(0.001)

            logger.info(
                "Slack message streamed successfully",
                channel=channel,
                content_length=len(content),
                chunk_size=chunk_size,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to stream Slack message",
                channel=channel,
                error=str(e),
            )
            return False
