"""Mock Knative Eventing Service for testing and CI environments."""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from cloudevents.http import CloudEvent
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared_models import configure_logging, simple_health_check

# Configure structured logging
logger = configure_logging("mock-eventing-service")


class EventSubscription(BaseModel):
    """Event subscription configuration."""

    event_type: str
    subscriber_url: str
    filter_attributes: Dict[str, str] = {}


class MockEventingService:
    """Mock Knative Eventing service that simulates broker behavior."""

    def __init__(self) -> None:
        self.subscriptions: List[EventSubscription] = []
        self.event_history: List[Dict[str, Any]] = []
        self.delivery_attempts: Dict[str, int] = {}

    def add_subscription(self, subscription: EventSubscription) -> None:
        """Add an event subscription."""
        self.subscriptions.append(subscription)
        logger.info(
            "Added event subscription",
            event_type=subscription.event_type,
            subscriber_url=subscription.subscriber_url,
            filter_attributes=subscription.filter_attributes,
        )

    def remove_subscription(self, event_type: str, subscriber_url: str) -> None:
        """Remove an event subscription."""
        self.subscriptions = [
            sub
            for sub in self.subscriptions
            if not (
                sub.event_type == event_type and sub.subscriber_url == subscriber_url
            )
        ]
        logger.info(
            "Removed event subscription",
            event_type=event_type,
            subscriber_url=subscriber_url,
        )

    async def publish_event(self, event: CloudEvent) -> bool:
        """Publish an event to all matching subscribers."""
        event_type = event.get("type")
        event_id = event.get("id", str(uuid.uuid4()))

        logger.info(
            "Publishing event",
            event_id=event_id,
            event_type=event_type,
            source=event.get("source"),
        )

        # Store event in history
        event_record = {
            "id": event_id,
            "type": event_type,
            "source": event.get("source"),
            "subject": event.get("subject"),
            "time": event.get("time"),
            "data": event.data,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        self.event_history.append(event_record)

        # Find matching subscriptions
        matching_subscriptions = []
        for subscription in self.subscriptions:
            if subscription.event_type == event_type:
                # Check filter attributes if any
                matches_filter = True
                for attr_key, attr_value in subscription.filter_attributes.items():
                    if event.get(attr_key) != attr_value:
                        matches_filter = False
                        break

                if matches_filter:
                    matching_subscriptions.append(subscription)

        logger.info(
            "Found matching subscriptions",
            event_id=event_id,
            event_type=event_type,
            subscription_count=len(matching_subscriptions),
        )

        # Deliver to all matching subscribers asynchronously
        for subscription in matching_subscriptions:
            # Create async task for each delivery (non-blocking)
            asyncio.create_task(self._deliver_event_async(event, subscription))

        # Return immediately - events are processed in background
        return True

    async def _deliver_event_async(
        self, event: CloudEvent, subscription: EventSubscription
    ) -> None:
        """Deliver an event to a specific subscriber asynchronously."""
        import httpx

        event_id = event.get("id", str(uuid.uuid4()))
        delivery_key = f"{event_id}:{subscription.subscriber_url}"

        # Track delivery attempts
        self.delivery_attempts[delivery_key] = (
            self.delivery_attempts.get(delivery_key, 0) + 1
        )
        attempt_count = self.delivery_attempts[delivery_key]

        logger.info(
            "Delivering event to subscriber (async)",
            event_id=event_id,
            subscriber_url=subscription.subscriber_url,
            attempt=attempt_count,
        )

        try:
            # Convert CloudEvent to HTTP format
            from cloudevents.http import to_structured

            logger.info(
                "Converting CloudEvent for delivery",
                event_id=event_id,
                event_data_preview=(
                    str(event.get_data())[:200] if event.get_data() else "no_data"
                ),
            )

            headers, body = to_structured(event)

            # Add mock broker headers
            headers["ce-broker"] = "mock-broker"
            headers["ce-delivery"] = str(attempt_count)

            logger.info(
                "Sending CloudEvent to subscriber",
                event_id=event_id,
                subscriber_url=subscription.subscriber_url,
                body_length=len(body),
                body_preview=body[:200] if body else "empty",
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    subscription.subscriber_url,
                    headers=headers,
                    content=body,
                )

                response.raise_for_status()

                logger.info(
                    "Event delivered successfully",
                    event_id=event_id,
                    subscriber_url=subscription.subscriber_url,
                    status_code=response.status_code,
                )

        except Exception as e:
            logger.error(
                "Failed to deliver event",
                event_id=event_id,
                subscriber_url=subscription.subscriber_url,
                attempt=attempt_count,
                error=str(e),
            )

            # In mock mode, we'll simulate some failures for testing
            if attempt_count < 3 and "timeout" in str(e).lower():
                logger.info("Simulating retry for testing purposes")

    async def _deliver_event(
        self, event: CloudEvent, subscription: EventSubscription
    ) -> bool:
        """Deliver an event to a specific subscriber (legacy method for compatibility)."""
        # This method is kept for compatibility but now just creates an async task
        asyncio.create_task(self._deliver_event_async(event, subscription))
        return True


# Initialize the mock service
mock_service = MockEventingService()


# Auto-create default subscriptions on startup
async def initialize_default_subscriptions() -> None:
    """Initialize default subscriptions for the mock eventing service."""
    try:
        # Get the service name from environment
        service_name = os.getenv("SERVICE_NAME", "self-service-agent")
        namespace = os.getenv("NAMESPACE", "default")

        # Default subscriptions that should always exist
        default_subscriptions: list[dict[str, Any]] = [
            {
                "event_type": "com.self-service-agent.request.created",
                "subscriber_url": f"http://{service_name}-agent-service.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {},
            },
            {
                "event_type": "com.self-service-agent.agent.response-ready",
                "subscriber_url": f"http://{service_name}-integration-dispatcher.{namespace}.svc.cluster.local",
                "filter_attributes": {"source": "request-manager"},
            },
            {
                "event_type": "com.self-service-agent.request.created",
                "subscriber_url": f"http://{service_name}-agent-service.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {"requiresrouting": "true"},
            },
            {
                "event_type": "com.self-service-agent.agent.response-ready",
                "subscriber_url": f"http://{service_name}-request-manager.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {"source": "agent-service"},
            },
            {
                "event_type": "com.self-service-agent.request.created",
                "subscriber_url": f"http://{service_name}-integration-dispatcher.{namespace}.svc.cluster.local/notifications",
                "filter_attributes": {},
            },
            {
                "event_type": "com.self-service-agent.request.processing",
                "subscriber_url": f"http://{service_name}-integration-dispatcher.{namespace}.svc.cluster.local/notifications",
                "filter_attributes": {},
            },
            {
                "event_type": "com.self-service-agent.request.database-update",
                "subscriber_url": f"http://{service_name}-agent-service.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {"source": "request-manager"},
            },
            # Responses mode event subscriptions
            {
                "event_type": "com.self-service-agent.responses.request.created",
                "subscriber_url": f"http://{service_name}-agent-service.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {},
            },
            {
                "event_type": "com.self-service-agent.responses.response.ready",
                "subscriber_url": f"http://{service_name}-request-manager.{namespace}.svc.cluster.local/api/v1/events/cloudevents",
                "filter_attributes": {"source": "agent-service"},
            },
            {
                "event_type": "com.self-service-agent.responses.response.ready",
                "subscriber_url": f"http://{service_name}-integration-dispatcher.{namespace}.svc.cluster.local",
                "filter_attributes": {"source": "request-manager"},
            },
        ]

        for sub_data in default_subscriptions:
            subscription = EventSubscription(**sub_data)
            mock_service.add_subscription(subscription)

        logger.info(
            "Initialized default subscriptions", count=len(default_subscriptions)
        )

    except Exception as e:
        logger.error("Failed to initialize default subscriptions", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="Mock Knative Eventing Service",
    description="Mock service that simulates Knative Broker behavior for testing and CI",
    version="0.1.0",
)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the service on startup."""
    await initialize_default_subscriptions()


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return await simple_health_check(
        service_name="mock-eventing-service",
        version="0.1.0",
    )


@app.post("/{namespace}/{broker_name}")
async def broker_endpoint(
    namespace: str,
    broker_name: str,
    request: Request,
) -> Dict[str, Any]:
    """Mock Knative Broker endpoint that accepts CloudEvents."""
    try:
        # Parse CloudEvent from request
        headers = dict(request.headers)
        body = await request.body()

        logger.info(
            "Received CloudEvent",
            content_type=headers.get("content-type"),
            body_length=len(body),
            body_preview=body[:200] if body else "empty",
        )

        # Parse CloudEvent
        if headers.get("content-type", "").startswith("application/cloudevents+json"):
            event_data = json.loads(body)

            # Debug: Log the raw event data structure
            logger.info(
                "Raw CloudEvent data structure",
                event_id=event_data.get("id"),
                event_type=event_data.get("type"),
                has_data_field="data" in event_data,
                data_field_type=(
                    type(event_data.get("data")).__name__
                    if "data" in event_data
                    else "missing"
                ),
                data_preview=(
                    str(event_data.get("data"))[:200]
                    if event_data.get("data")
                    else "no_data_field"
                ),
            )

            # For structured CloudEvents, we need to handle the data field properly
            # The CloudEvent constructor expects the data to be passed separately
            event_data_field = event_data.get("data")
            event_attributes = {k: v for k, v in event_data.items() if k != "data"}

            # Create CloudEvent with proper data handling
            if event_data_field is not None:
                event = CloudEvent(event_attributes, event_data_field)
            else:
                event = CloudEvent(event_attributes)

            # Debug: Check if the CloudEvent has data after construction
            logger.info(
                "CloudEvent construction debug",
                event_id=event.get("id"),
                has_data=hasattr(event, "data"),
                data_type=(
                    type(getattr(event, "data", None)).__name__
                    if hasattr(event, "data")
                    else "no_data_attr"
                ),
                data_value=(
                    str(getattr(event, "data", None))[:200]
                    if hasattr(event, "data") and getattr(event, "data")
                    else "no_data_value"
                ),
            )
            logger.info(
                "Parsed structured CloudEvent",
                event_id=event.get("id"),
                event_type=event.get("type"),
                data_preview=(
                    str(event.get_data())[:200] if event.get_data() else "no_data"
                ),
            )
        else:
            # Binary format
            ce_headers = {
                key[3:].lower(): value  # Remove 'ce-' prefix and lowercase
                for key, value in headers.items()
                if key.lower().startswith("ce-")
            }

            # Parse body data properly
            body_data = None
            if body:
                try:
                    body_data = json.loads(body)
                except json.JSONDecodeError as e:
                    logger.error(
                        "Failed to parse CloudEvent body as JSON", error=str(e)
                    )
                    body_data = body.decode("utf-8") if body else None

            event = CloudEvent(ce_headers, body_data)
            logger.info(
                "Parsed binary CloudEvent",
                event_id=event.get("id"),
                event_type=event.get("type"),
                data_preview=(
                    str(event.get_data())[:200] if event.get_data() else "no_data"
                ),
            )

        # Publish the event
        success = await mock_service.publish_event(event)

        if success:
            return {"status": "accepted", "message": "Event published successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to publish event",
            )

    except Exception as e:
        logger.error("Failed to process broker request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


@app.post("/subscriptions")
async def add_subscription(subscription: EventSubscription) -> Dict[str, Any]:
    """Add an event subscription."""
    mock_service.add_subscription(subscription)
    return {"status": "created", "subscription": subscription.model_dump()}


@app.delete("/subscriptions")
async def remove_subscription(
    event_type: str,
    subscriber_url: str,
) -> Dict[str, Any]:
    """Remove an event subscription."""
    mock_service.remove_subscription(event_type, subscriber_url)
    return {
        "status": "deleted",
        "event_type": event_type,
        "subscriber_url": subscriber_url,
    }


@app.get("/subscriptions")
async def list_subscriptions() -> Dict[str, Any]:
    """List all event subscriptions."""
    return {
        "subscriptions": [sub.model_dump() for sub in mock_service.subscriptions],
        "count": len(mock_service.subscriptions),
    }


@app.get("/events")
async def list_events(limit: int = 100) -> Dict[str, Any]:
    """List recent events."""
    recent_events = (
        mock_service.event_history[-limit:] if mock_service.event_history else []
    )
    return {
        "events": recent_events,
        "count": len(recent_events),
        "total": len(mock_service.event_history),
    }


@app.delete("/events")
async def clear_events() -> dict[str, str]:
    """Clear event history."""
    mock_service.event_history.clear()
    mock_service.delivery_attempts.clear()
    return {"status": "cleared", "message": "Event history cleared"}


@app.post("/reset")
async def reset_service() -> dict[str, str]:
    """Reset the mock service to initial state."""
    mock_service.subscriptions.clear()
    mock_service.event_history.clear()
    mock_service.delivery_attempts.clear()
    return {"status": "reset", "message": "Mock service reset to initial state"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("Starting Mock Knative Eventing Service", host=host, port=port)

    uvicorn.run(
        "mock_eventing_service.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
