"""Shared CloudEvent utilities for all services."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from cloudevents.http import CloudEvent, to_structured

logger = structlog.get_logger()


# CloudEvent type constants
class EventTypes:
    """CloudEvent type constants for the self-service agent system."""

    # Request events
    REQUEST_CREATED = "com.self-service-agent.request.created"
    REQUEST_PROCESSING = "com.self-service-agent.request.processing"

    # Response events
    AGENT_RESPONSE_READY = "com.self-service-agent.agent.response-ready"

    # Database update events
    DATABASE_UPDATE_REQUESTED = "com.self-service-agent.request.database-update"


class CloudEventBuilder:
    """Builder for creating standardized CloudEvents."""

    def __init__(self, source: str, service_name: str = "self-service-agent"):
        self.source = source
        self.service_name = service_name
        self.base_attributes = {
            "source": source,
            "specversion": "1.0",
            "datacontenttype": "application/json",
        }

    def create_request_event(
        self,
        request_data: Dict[str, Any],
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> CloudEvent:
        """Create a request created event."""
        event_id = request_id or str(uuid.uuid4())

        attributes = {
            **self.base_attributes,
            "type": EventTypes.REQUEST_CREATED,
            "id": event_id,
            "time": datetime.now(timezone.utc).isoformat(),
        }

        # Add optional attributes
        if user_id:
            attributes["userid"] = user_id
        if session_id:
            attributes["sessionid"] = session_id

        return CloudEvent(attributes, request_data)

    def create_response_event(
        self,
        response_data: Dict[str, Any],
        request_id: str,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> CloudEvent:
        """Create an agent response ready event."""
        attributes = {
            **self.base_attributes,
            "type": EventTypes.AGENT_RESPONSE_READY,
            "id": str(uuid.uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "requestid": request_id,
        }

        # Add optional attributes
        if agent_id:
            attributes["agentid"] = agent_id
        if session_id:
            attributes["sessionid"] = session_id

        return CloudEvent(attributes, response_data)


class CloudEventValidator:
    """Validator for CloudEvent processing."""

    @staticmethod
    def validate_request_event(event: CloudEvent) -> bool:
        """Validate a request created event."""
        required_attributes = ["type", "id", "time", "source"]
        required_type = EventTypes.REQUEST_CREATED

        return (
            all(attr in event for attr in required_attributes)
            and event["type"] == required_type
        )

    @staticmethod
    def validate_response_event(event: CloudEvent) -> bool:
        """Validate an agent response ready event."""
        required_attributes = ["type", "id", "time", "source", "requestid"]
        required_type = EventTypes.AGENT_RESPONSE_READY

        return (
            all(attr in event for attr in required_attributes)
            and event["type"] == required_type
        )


class CloudEventProcessor:
    """Processor for handling CloudEvents."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.builder = CloudEventBuilder(service_name, service_name)
        self.validator = CloudEventValidator()

    def process_request_event(self, event: CloudEvent) -> Optional[Dict[str, Any]]:
        """Process a request created event."""
        if not self.validator.validate_request_event(event):
            logger.error("Invalid request event", event_type=event.get("type"))
            return None

        logger.info(
            "Processing request event",
            event_id=event["id"],
            user_id=event.get("userid"),
            session_id=event.get("sessionid"),
        )

        return event.data

    def process_response_event(self, event: CloudEvent) -> Optional[Dict[str, Any]]:
        """Process an agent response ready event."""
        if not self.validator.validate_response_event(event):
            logger.error("Invalid response event", event_type=event.get("type"))
            return None

        logger.info(
            "Processing response event",
            event_id=event["id"],
            request_id=event["requestid"],
            agent_id=event.get("agentid"),
        )

        return event.data


class CloudEventSender:
    """Sender for CloudEvents to brokers."""

    def __init__(self, broker_url: str, service_name: str):
        self.broker_url = broker_url
        self.service_name = service_name
        self.builder = CloudEventBuilder(service_name, service_name)

    async def send_request_event(
        self,
        request_data: Dict[str, Any],
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Send a request created event."""
        try:
            event = self.builder.create_request_event(
                request_data, request_id, user_id, session_id
            )
            return await self._send_event(event)
        except Exception as e:
            logger.error("Failed to send request event", error=str(e))
            return False

    async def send_response_event(
        self,
        response_data: Dict[str, Any],
        request_id: str,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Send an agent response ready event."""
        try:
            event = self.builder.create_response_event(
                response_data, request_id, agent_id, session_id
            )
            return await self._send_event(event)
        except Exception as e:
            logger.error("Failed to send response event", error=str(e))
            return False

    async def _send_event(self, event: CloudEvent) -> bool:
        """Send a CloudEvent to the broker."""
        try:
            import httpx

            logger.debug(
                "Sending CloudEvent to broker",
                broker_url=self.broker_url,
                event_type=event["type"],
                event_id=event["id"],
            )

            # Convert to structured format
            headers, data = to_structured(event)

            async with httpx.AsyncClient() as client:
                logger.debug(
                    "Making HTTP POST request to broker", broker_url=self.broker_url
                )
                response = await client.post(
                    self.broker_url,
                    headers=headers,
                    content=data,
                    timeout=30.0,
                )
                logger.debug(
                    "HTTP response received",
                    status_code=response.status_code,
                    broker_url=self.broker_url,
                )
                response.raise_for_status()

                logger.debug(
                    "CloudEvent sent successfully",
                    event_type=event["type"],
                    event_id=event["id"],
                    status_code=response.status_code,
                )
                return True

        except Exception as e:
            logger.error(
                "Failed to send CloudEvent",
                event_type=event["type"],
                event_id=event["id"],
                broker_url=self.broker_url,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False


# Convenience functions for common CloudEvent operations
def create_request_event(
    source: str,
    request_data: Dict[str, Any],
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> CloudEvent:
    """Create a standardized request event."""
    builder = CloudEventBuilder(source)
    return builder.create_request_event(request_data, request_id, user_id, session_id)


def create_response_event(
    source: str,
    response_data: Dict[str, Any],
    request_id: str,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> CloudEvent:
    """Create a standardized response event."""
    builder = CloudEventBuilder(source)
    return builder.create_response_event(
        response_data, request_id, agent_id, session_id
    )


def validate_event_type(event: CloudEvent, expected_type: str) -> bool:
    """Validate that an event has the expected type."""
    return event.get("type") == expected_type


def extract_event_context(event: CloudEvent) -> Dict[str, Any]:
    """Extract common context from an event."""
    return {
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "source": event.get("source"),
        "time": event.get("time"),
        "request_id": event.get("requestid"),
        "user_id": event.get("userid"),
        "session_id": event.get("sessionid"),
        "agent_id": event.get("agentid"),
    }
