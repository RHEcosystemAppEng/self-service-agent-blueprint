"""CloudEvents integration for event-driven communication."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from cloudevents.http import CloudEvent, to_structured
from cloudevents.http.event import CloudEvent as CloudEventType
from shared_models import EventTypes, configure_logging

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


# Global event publisher instance
_event_publisher: Optional[CloudEventPublisher] = None


def get_event_publisher() -> CloudEventPublisher:
    """Get the global event publisher instance."""
    global _event_publisher
    if _event_publisher is None:
        config = EventConfig()
        _event_publisher = CloudEventPublisher(config)
    return _event_publisher
