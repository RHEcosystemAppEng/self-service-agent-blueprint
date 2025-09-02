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


def validate_cloudevent_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Validate and extract CloudEvent headers.

    Args:
        headers: Request headers dictionary

    Returns:
        Extracted CloudEvent headers

    Raises:
        HTTPException: If required headers are missing
    """
    required_headers = ["ce-id", "ce-source", "ce-type", "ce-specversion"]
    extracted = {}

    for header in required_headers:
        value = headers.get(header)
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required CloudEvent header: {header}",
            )
        extracted[header] = value

    # Optional headers
    optional_headers = ["ce-time", "ce-datacontenttype", "ce-dataschema", "ce-subject"]
    for header in optional_headers:
        value = headers.get(header)
        if value:
            extracted[header] = value

    return extracted


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
    response = {
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if details:
        response["details"] = details

    return response
