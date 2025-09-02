"""Mock Knative Eventing Service for testing and CI environments."""

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

    def __init__(self):
        self.subscriptions: List[EventSubscription] = []
        self.event_history: List[Dict[str, Any]] = []
        self.delivery_attempts: Dict[str, int] = {}

    def add_subscription(self, subscription: EventSubscription):
        """Add an event subscription."""
        self.subscriptions.append(subscription)
        logger.info(
            "Added event subscription",
            event_type=subscription.event_type,
            subscriber_url=subscription.subscriber_url,
            filter_attributes=subscription.filter_attributes,
        )

    def remove_subscription(self, event_type: str, subscriber_url: str):
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

        # Deliver to all matching subscribers
        delivery_success = True
        for subscription in matching_subscriptions:
            success = await self._deliver_event(event, subscription)
            if not success:
                delivery_success = False

        return delivery_success

    async def _deliver_event(
        self, event: CloudEvent, subscription: EventSubscription
    ) -> bool:
        """Deliver an event to a specific subscriber."""
        import httpx

        event_id = event.get("id", str(uuid.uuid4()))
        delivery_key = f"{event_id}:{subscription.subscriber_url}"

        # Track delivery attempts
        self.delivery_attempts[delivery_key] = (
            self.delivery_attempts.get(delivery_key, 0) + 1
        )
        attempt_count = self.delivery_attempts[delivery_key]

        logger.info(
            "Delivering event to subscriber",
            event_id=event_id,
            subscriber_url=subscription.subscriber_url,
            attempt=attempt_count,
        )

        try:
            # Convert CloudEvent to HTTP format
            from cloudevents.http import to_structured

            headers, body = to_structured(event)

            # Add mock broker headers
            headers["ce-broker"] = "mock-broker"
            headers["ce-delivery"] = str(attempt_count)

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

                return True

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
                return False

            return False


# Initialize the mock service
mock_service = MockEventingService()

# Create FastAPI application
app = FastAPI(
    title="Mock Knative Eventing Service",
    description="Mock service that simulates Knative Broker behavior for testing and CI",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
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
):
    """Mock Knative Broker endpoint that accepts CloudEvents."""
    try:
        # Parse CloudEvent from request
        headers = dict(request.headers)
        body = await request.body()

        # Parse CloudEvent
        if headers.get("content-type", "").startswith("application/cloudevents+json"):
            event_data = json.loads(body)
            event = CloudEvent(event_data)
        else:
            # Binary format
            ce_headers = {
                key[3:].lower(): value  # Remove 'ce-' prefix and lowercase
                for key, value in headers.items()
                if key.lower().startswith("ce-")
            }
            event = CloudEvent(ce_headers, json.loads(body) if body else None)

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
async def add_subscription(subscription: EventSubscription):
    """Add an event subscription."""
    mock_service.add_subscription(subscription)
    return {"status": "created", "subscription": subscription.model_dump()}


@app.delete("/subscriptions")
async def remove_subscription(
    event_type: str,
    subscriber_url: str,
):
    """Remove an event subscription."""
    mock_service.remove_subscription(event_type, subscriber_url)
    return {
        "status": "deleted",
        "event_type": event_type,
        "subscriber_url": subscriber_url,
    }


@app.get("/subscriptions")
async def list_subscriptions():
    """List all event subscriptions."""
    return {
        "subscriptions": [sub.model_dump() for sub in mock_service.subscriptions],
        "count": len(mock_service.subscriptions),
    }


@app.get("/events")
async def list_events(limit: int = 100):
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
async def clear_events():
    """Clear event history."""
    mock_service.event_history.clear()
    mock_service.delivery_attempts.clear()
    return {"status": "cleared", "message": "Event history cleared"}


@app.post("/reset")
async def reset_service():
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
