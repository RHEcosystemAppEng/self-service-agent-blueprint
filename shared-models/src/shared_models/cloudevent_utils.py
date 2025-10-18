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
    def extract_request_data(request_data: Dict[str, Any]) -> tuple[Any, ...]:
        """Extract and validate request data from CloudEvents.

        Args:
            request_data: Request data from CloudEvent

        Returns:
            Tuple of (request_id, user_id, message, session_id)

        Raises:
            ValueError: If required fields are missing
        """
        request_id = request_data.get("request_id")
        user_id = request_data.get("user_id")
        message = request_data.get("message")
        session_id = request_data.get("request_manager_session_id")

        if not all([request_id, user_id, message]):
            raise ValueError("Missing required fields: request_id, user_id, message")

        return request_id, user_id, message, session_id

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


class RequestLogService:
    """Common utilities for request log operations."""

    @staticmethod
    async def create_log_entry(
        request_id: str,
        session_id: str,
        user_id: str,
        content: str,
        request_type: str,
        integration_type: str,
        db: Any,  # AsyncSession
        integration_context: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a unified request log entry.

        Args:
            request_id: Unique request identifier
            session_id: Session identifier
            user_id: User identifier
            content: Request content/message
            request_type: Type of request (e.g., "responses_api", "agent_api")
            integration_type: Integration type (e.g., "CLI", "Slack")
            db: Database session
            integration_context: Additional integration context
            **kwargs: Additional fields for the log entry
        """
        from .models import RequestLog

        integration_context = integration_context or {}

        log_entry = RequestLog(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            content=content,
            request_type=request_type,
            integration_type=integration_type,
            integration_context=integration_context,
            created_at=datetime.now(timezone.utc),
            **kwargs,
        )

        db.add(log_entry)
        await db.commit()

    @staticmethod
    async def update_log_entry(
        request_id: str,
        response_content: str,
        agent_id: str,
        processing_time_ms: int,
        db: Any,  # AsyncSession
        response_metadata: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Update a request log entry with response information.

        Args:
            request_id: Unique request identifier
            response_content: Agent response content
            agent_id: Agent that processed the request
            processing_time_ms: Processing time in milliseconds
            db: Database session
            response_metadata: Additional response metadata
            **kwargs: Additional fields for the log entry
        """
        from sqlalchemy import update

        from .models import RequestLog

        response_metadata = response_metadata or {}

        stmt = (
            update(RequestLog)
            .where(RequestLog.request_id == request_id)
            .values(
                response_content=response_content,
                agent_id=agent_id,
                processing_time_ms=processing_time_ms,
                response_metadata=response_metadata,
                **kwargs,
            )
        )

        await db.execute(stmt)
        await db.commit()
