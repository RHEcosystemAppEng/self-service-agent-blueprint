"""CloudEvents integration for event-driven communication."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import httpx
from cloudevents.http import CloudEvent, to_structured
from cloudevents.http.event import CloudEvent as CloudEventType
from shared_models import EventTypes, configure_logging, get_enum_value
from shared_models.models import AgentResponse, NormalizedRequest

logger = configure_logging("request-manager")


def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and should be retried."""
    if isinstance(error, httpx.HTTPStatusError):
        # Retry on server errors (5xx) and some client errors
        status_code = error.response.status_code
        return status_code >= 500 or status_code in [408, 429]  # Timeout, Rate Limited

    if isinstance(error, (httpx.ConnectError, httpx.TimeoutException)):
        # Network connectivity issues are usually transient
        return True

    if isinstance(error, OSError):
        # OS-level network errors (like EOF) are often transient
        return True

    # Default to non-transient for unknown errors
    return False


class EventConfig:
    """Configuration for event handling."""

    def __init__(self) -> None:
        # Knative Broker endpoint - can be optional for fallback mode
        import os

        self.broker_url = os.getenv("BROKER_URL")
        self.eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"

        # If eventing is disabled, we don't need a broker URL
        if self.eventing_enabled and not self.broker_url:
            raise ValueError(
                "BROKER_URL environment variable is required when eventing is enabled. "
                "Set EVENTING_ENABLED=false to disable eventing or configure BROKER_URL."
            )

        self.source = "request-manager"
        self.timeout = 30.0

        # Retry configuration
        self.max_retries = int(os.getenv("EVENT_MAX_RETRIES", "3"))
        self.base_delay = float(os.getenv("EVENT_BASE_DELAY", "1.0"))
        self.max_delay = float(os.getenv("EVENT_MAX_DELAY", "30.0"))
        self.backoff_multiplier = float(os.getenv("EVENT_BACKOFF_MULTIPLIER", "2.0"))


class CloudEventPublisher:
    """Publishes CloudEvents to Knative Broker."""

    def __init__(self, config: EventConfig) -> None:
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout)

    async def publish_request_event(
        self,
        normalized_request: NormalizedRequest,
        event_type: str = EventTypes.REQUEST_CREATED,
    ) -> bool:
        """Publish a normalized request as a CloudEvent."""
        # If eventing is disabled, return success without publishing
        if not self.config.eventing_enabled:
            logger.info(
                "Eventing disabled - skipping event publication",
                event_type=event_type,
                request_id=normalized_request.request_id,
            )
            return True

        event_data = {
            "request_id": normalized_request.request_id,
            "session_id": normalized_request.session_id,
            "user_id": normalized_request.user_id,
            "integration_type": get_enum_value(normalized_request.integration_type),
            "request_type": normalized_request.request_type,
            "content": normalized_request.content,
            "integration_context": normalized_request.integration_context,
            "user_context": normalized_request.user_context,
            "target_agent_id": normalized_request.target_agent_id,
            "requires_routing": normalized_request.requires_routing,
            "created_at": normalized_request.created_at.isoformat(),
        }

        event = CloudEvent(
            {
                "specversion": "1.0",
                "type": event_type,
                "source": self.config.source,
                "id": str(uuid.uuid4()),
                "time": datetime.now(timezone.utc).isoformat(),
                "subject": f"session/{normalized_request.session_id}",
                "datacontenttype": "application/json",
            },
            event_data,
        )

        return await self._publish_event(event)

    async def publish_response_event(
        self,
        agent_response: AgentResponse,
        event_type: str = EventTypes.AGENT_RESPONSE_READY,
    ) -> bool:
        """Publish an agent response as a CloudEvent."""
        # If eventing is disabled, return success without publishing
        if not self.config.eventing_enabled:
            logger.info(
                "Eventing disabled - skipping event publication",
                event_type=event_type,
                request_id=agent_response.request_id,
            )
            return True

        event_data = {
            "request_id": agent_response.request_id,
            "session_id": agent_response.session_id,
            "agent_id": agent_response.agent_id,
            "content": agent_response.content,
            "response_type": agent_response.response_type,
            "metadata": agent_response.metadata,
            "processing_time_ms": agent_response.processing_time_ms,
            "requires_followup": agent_response.requires_followup,
            "followup_actions": agent_response.followup_actions,
            "created_at": agent_response.created_at.isoformat(),
        }

        event = CloudEvent(
            {
                "specversion": "1.0",
                "type": event_type,
                "source": self.config.source,
                "id": str(uuid.uuid4()),
                "time": datetime.now(timezone.utc).isoformat(),
                "subject": f"session/{agent_response.session_id}",
                "datacontenttype": "application/json",
            },
            event_data,
        )

        return await self._publish_event(event)

    async def publish_database_update_event(self, update_data: Dict[str, Any]) -> bool:
        """Publish database update event to Agent Service."""
        # If eventing is disabled, return success without publishing
        if not self.config.eventing_enabled:
            logger.info(
                "Eventing disabled - skipping database update event publication",
                request_id=update_data.get("request_id"),
            )
            return True

        event = CloudEvent(
            {
                "specversion": "1.0",
                "type": EventTypes.DATABASE_UPDATE_REQUESTED,
                "source": self.config.source,
                "id": str(uuid.uuid4()),
                "time": datetime.now(timezone.utc).isoformat(),
                "subject": f"request/{update_data.get('request_id')}",
                "datacontenttype": "application/json",
            },
            update_data,
        )

        return await self._publish_event(event)

    async def publish_session_event(
        self,
        session_id: str,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> bool:
        """Publish a session-related event."""
        # If eventing is disabled, return success without publishing
        if not self.config.eventing_enabled:
            logger.info(
                "Eventing disabled - skipping event publication",
                event_type=event_type,
                session_id=session_id,
            )
            return True

        event = CloudEvent(
            {
                "specversion": "1.0",
                "type": event_type,
                "source": self.config.source,
                "id": str(uuid.uuid4()),
                "time": datetime.now(timezone.utc).isoformat(),
                "subject": f"session/{session_id}",
                "datacontenttype": "application/json",
            },
            event_data,
        )

        return await self._publish_event(event)

    async def _publish_event(self, event: CloudEventType) -> bool:
        """Publish a CloudEvent to the broker with retry logic."""
        headers, body = to_structured(event)
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    "Publishing CloudEvent",
                    event_type=event.get("type"),
                    event_id=event.get("id"),
                    attempt=attempt + 1,
                    max_attempts=self.config.max_retries + 1,
                )

                if not self.config.broker_url:
                    raise ValueError("Broker URL is not configured")

                response = await self.client.post(
                    self.config.broker_url,
                    headers=headers,
                    content=body,
                )

                response.raise_for_status()

                if attempt > 0:
                    logger.info(
                        "CloudEvent published successfully after retry",
                        event_type=event.get("type"),
                        event_id=event.get("id"),
                        attempt=attempt + 1,
                    )

                return True

            except Exception as e:
                last_error = e

                # Log the error with context
                logger.warning(
                    "Failed to publish CloudEvent",
                    event_type=event.get("type"),
                    event_id=event.get("id"),
                    attempt=attempt + 1,
                    max_attempts=self.config.max_retries + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # Check if we should retry
                if attempt < self.config.max_retries and is_transient_error(e):
                    # Calculate delay with exponential backoff
                    delay = min(
                        self.config.base_delay
                        * (self.config.backoff_multiplier**attempt),
                        self.config.max_delay,
                    )

                    logger.info(
                        "Retrying CloudEvent publish after delay",
                        event_type=event.get("type"),
                        event_id=event.get("id"),
                        delay_seconds=delay,
                        next_attempt=attempt + 2,
                    )

                    await asyncio.sleep(delay)
                else:
                    # Either max retries reached or non-transient error
                    break

        # All retries exhausted or non-transient error
        logger.error(
            "Failed to publish CloudEvent after all retries",
            event_type=event.get("type"),
            event_id=event.get("id"),
            total_attempts=self.config.max_retries + 1,
            final_error=str(last_error),
            error_type=type(last_error).__name__,
            is_transient=is_transient_error(last_error) if last_error else False,
        )

        return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


class CloudEventHandler:
    """Handles incoming CloudEvents."""

    def __init__(self) -> None:
        self.handlers: Dict[str, Callable[..., Any]] = {}

    def register_handler(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Register a handler for a specific event type."""
        self.handlers[event_type] = handler

    async def handle_event(self, event: CloudEventType) -> Optional[Dict[str, Any]]:
        """Handle an incoming CloudEvent."""
        event_type = event.get("type")

        if event_type not in self.handlers:
            logger.warning(
                "No handler registered for event type", event_type=event_type
            )
            return None

        handler = self.handlers[event_type]

        try:
            result = await handler(event)
            return result if isinstance(result, dict) else None
        except Exception as e:
            logger.error("Error handling event", event_type=event_type, error=str(e))
            return None

    def parse_cloudevent_from_request(
        self, headers: Dict[str, str], body: bytes
    ) -> Optional[CloudEventType]:
        """Parse a CloudEvent from HTTP request headers and body."""
        try:
            # Try structured content first
            if headers.get("content-type", "").startswith(
                "application/cloudevents+json"
            ):
                event_data = json.loads(body)
                return CloudEvent(event_data)

            # Try binary content
            ce_headers = {
                key[3:].lower(): value  # Remove 'ce-' prefix and lowercase
                for key, value in headers.items()
                if key.lower().startswith("ce-")
            }

            if ce_headers:
                return CloudEvent(ce_headers, json.loads(body) if body else None)

            return None

        except Exception as e:
            logger.error("Failed to parse CloudEvent", error=str(e))
            return None


# Global event publisher instance
_event_publisher: Optional[CloudEventPublisher] = None


def get_event_publisher() -> CloudEventPublisher:
    """Get the global event publisher instance."""
    global _event_publisher
    if _event_publisher is None:
        config = EventConfig()
        _event_publisher = CloudEventPublisher(config)
    return _event_publisher
