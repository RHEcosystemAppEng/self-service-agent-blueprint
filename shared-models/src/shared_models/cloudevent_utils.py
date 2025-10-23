"""CloudEvent utilities for shared event handling patterns."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cloudevents.http import from_http
from fastapi import HTTPException, Request, status

from .logging import configure_logging

logger = configure_logging("cloudevent-utils")


async def parse_cloudevent_from_request(request: Request) -> Dict[str, Any]:
    """
    Parse CloudEvent from HTTP request with standardized error handling.

    Args:
        request: FastAPI Request object

    Returns:
        Parsed CloudEvent data as dictionary

    Raises:
        HTTPException: If parsing fails
    """
    try:
        # Get request body
        body = await request.body()
        if not body:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Empty request body"
            )

        # Parse CloudEvent from HTTP headers and body
        event = from_http(headers=dict(request.headers), data=body)

        if not event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CloudEvent format",
            )

        # Debug log the raw CloudEvent to see what's happening
        logger.debug(
            "Raw CloudEvent details",
            event_id=event.get("id"),
            event_type=event.get("type"),
            event_source=event.get("source"),
            event_data_raw=event.get_data(),
            event_data_type=type(event.get_data()),
            event_attrs=list(event.keys()) if hasattr(event, "keys") else "no_keys",
        )

        # Convert to dictionary for easier handling
        event_data = {
            "id": event.get("id"),
            "source": event.get("source"),
            "type": event.get("type"),
            "specversion": event.get("specversion"),
            "time": event.get("time"),
            "data": event.get_data(),
            "datacontenttype": event.get("datacontenttype"),
            "dataschema": event.get("dataschema"),
            "subject": event.get("subject"),
        }

        # Log successful parsing
        logger.debug(
            "CloudEvent parsed successfully",
            event_id=event_data.get("id"),
            event_type=event_data.get("type"),
            event_source=event_data.get("source"),
        )

        return event_data

    except json.JSONDecodeError as e:
        logger.error("Failed to parse CloudEvent JSON", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in CloudEvent: {str(e)}",
        )
    except Exception as e:
        logger.error("Failed to parse CloudEvent", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CloudEvent parsing failed: {str(e)}",
        )


async def create_cloudevent_response(
    status: str = "success",
    message: str = "CloudEvent processed successfully",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a standardized CloudEvent response.

    Args:
        status: Response status
        message: Response message
        details: Additional response details

    Returns:
        Standardized response dictionary
    """
    response: Dict[str, Any] = {
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if details:
        response["details"] = details

    return response


class CloudEventHandler:
    """Common utilities for CloudEvents handling."""

    @staticmethod
    def extract_event_data(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and validate event data with common logging.

        Args:
            event_data: Raw CloudEvent data dictionary

        Returns:
            Extracted request/response data from the event
        """
        request_data = event_data.get("data", {})

        # Ensure we return a dict
        if not isinstance(request_data, dict):
            request_data = {}

        logger.debug(
            "Processing event data",
            request_data_keys=(
                list(request_data.keys())
                if isinstance(request_data, dict)
                else "not_dict"
            ),
            request_data_preview=str(request_data)[:200] if request_data else "empty",
        )

        return request_data

    @staticmethod
    def extract_response_data(response_data: Dict[str, Any]) -> tuple[Any, ...]:
        """Extract and validate response data from CloudEvents.

        Args:
            response_data: Response data from CloudEvent

        Returns:
            Tuple of (request_id, session_id, agent_id, content, user_id)

        Raises:
            ValueError: If required fields are missing
        """
        from .utils import generate_fallback_user_id

        request_id = response_data.get("request_id")
        session_id = response_data.get("session_id")
        agent_id = response_data.get("agent_id")
        content = response_data.get("content")
        user_id = response_data.get("user_id")

        if not all([request_id, session_id, content]):
            raise ValueError("Missing required fields in response")

        # Handle missing user_id gracefully
        if not user_id:
            logger.warning(
                "Missing user_id in response event, using fallback",
                request_id=request_id,
                session_id=session_id,
            )
            user_id = generate_fallback_user_id(request_id)

        return request_id, session_id, agent_id, content, user_id

    @staticmethod
    def get_event_metadata(event_data: Dict[str, Any]) -> tuple[Any, ...]:
        """Extract common event metadata.

        Args:
            event_data: Raw CloudEvent data dictionary

        Returns:
            Tuple of (event_id, event_type, event_source)
        """
        event_id = event_data.get("id")
        event_type = event_data.get("type")
        event_source = event_data.get("source")

        return event_id, event_type, event_source
