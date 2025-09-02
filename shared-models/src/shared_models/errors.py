"""Shared error handling utilities for all services."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()


class ErrorResponse(BaseModel):
    """Standardized error response format."""

    error: str
    error_code: str
    detail: Optional[str] = None
    timestamp: str = None
    request_id: Optional[str] = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        super().__init__(**data)


class ServiceError(Exception):
    """Base exception for service-specific errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "SERVICE_ERROR",
        status_code: int = 500,
        detail: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id
        super().__init__(message)


class DatabaseError(ServiceError):
    """Database-related errors."""

    def __init__(
        self,
        message: str,
        detail: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=500,
            detail=detail,
            request_id=request_id,
        )


class SessionError(ServiceError):
    """Session-related errors."""

    def __init__(
        self,
        message: str,
        detail: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            error_code="SESSION_ERROR",
            status_code=500,
            detail=detail,
            request_id=request_id,
        )


class IntegrationError(ServiceError):
    """Integration-related errors."""

    def __init__(
        self,
        message: str,
        detail: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            error_code="INTEGRATION_ERROR",
            status_code=500,
            detail=detail,
            request_id=request_id,
        )


class AgentError(ServiceError):
    """Agent service-related errors."""

    def __init__(
        self,
        message: str,
        detail: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            error_code="AGENT_ERROR",
            status_code=500,
            detail=detail,
            request_id=request_id,
        )


def create_error_response(
    error: str,
    error_code: str = "INTERNAL_ERROR",
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
    status_code: int = 500,
) -> HTTPException:
    """Create a standardized HTTP exception with error response."""
    error_response = ErrorResponse(
        error=error,
        error_code=error_code,
        detail=detail,
        request_id=request_id,
    )

    return HTTPException(
        status_code=status_code,
        detail=error_response.dict(),
    )


def handle_service_error(error: ServiceError) -> HTTPException:
    """Convert ServiceError to HTTPException."""
    logger.error(
        "Service error occurred",
        error=error.message,
        error_code=error.error_code,
        detail=error.detail,
        request_id=error.request_id,
    )

    return HTTPException(
        status_code=error.status_code,
        detail=ErrorResponse(
            error=error.message,
            error_code=error.error_code,
            detail=error.detail,
            request_id=error.request_id,
        ).dict(),
    )


def handle_database_error(
    error: Exception, request_id: Optional[str] = None
) -> HTTPException:
    """Handle database errors with standardized response."""
    logger.error("Database error occurred", error=str(error), request_id=request_id)

    return create_error_response(
        error="Database operation failed",
        error_code="DATABASE_ERROR",
        detail=str(error),
        request_id=request_id,
        status_code=500,
    )


def handle_session_error(
    error: Exception, request_id: Optional[str] = None
) -> HTTPException:
    """Handle session errors with standardized response."""
    logger.error("Session error occurred", error=str(error), request_id=request_id)

    return create_error_response(
        error="Session operation failed",
        error_code="SESSION_ERROR",
        detail=str(error),
        request_id=request_id,
        status_code=500,
    )


def handle_integration_error(
    error: Exception, request_id: Optional[str] = None
) -> HTTPException:
    """Handle integration errors with standardized response."""
    logger.error("Integration error occurred", error=str(error), request_id=request_id)

    return create_error_response(
        error="Integration operation failed",
        error_code="INTEGRATION_ERROR",
        detail=str(error),
        request_id=request_id,
        status_code=500,
    )


def handle_agent_error(
    error: Exception, request_id: Optional[str] = None
) -> HTTPException:
    """Handle agent service errors with standardized response."""
    logger.error(
        "Agent service error occurred", error=str(error), request_id=request_id
    )

    return create_error_response(
        error="Agent service operation failed",
        error_code="AGENT_ERROR",
        detail=str(error),
        request_id=request_id,
        status_code=500,
    )


def handle_generic_error(
    error: Exception, request_id: Optional[str] = None
) -> HTTPException:
    """Handle generic errors with standardized response."""
    logger.error("Unexpected error occurred", error=str(error), request_id=request_id)

    return create_error_response(
        error="Internal server error",
        error_code="INTERNAL_ERROR",
        detail=str(error),
        request_id=request_id,
        status_code=500,
    )


# Common error responses
def create_not_found_error(
    resource: str, request_id: Optional[str] = None
) -> HTTPException:
    """Create a standardized 404 error."""
    return create_error_response(
        error=f"{resource} not found",
        error_code="NOT_FOUND",
        request_id=request_id,
        status_code=404,
    )


def create_validation_error(
    field: str, detail: str, request_id: Optional[str] = None
) -> HTTPException:
    """Create a standardized validation error."""
    return create_error_response(
        error=f"Validation error for {field}",
        error_code="VALIDATION_ERROR",
        detail=detail,
        request_id=request_id,
        status_code=400,
    )


def create_unauthorized_error(
    detail: str = "Authentication required", request_id: Optional[str] = None
) -> HTTPException:
    """Create a standardized 401 error."""
    return create_error_response(
        error="Unauthorized",
        error_code="UNAUTHORIZED",
        detail=detail,
        request_id=request_id,
        status_code=401,
    )


def create_forbidden_error(
    detail: str = "Access forbidden", request_id: Optional[str] = None
) -> HTTPException:
    """Create a standardized 403 error."""
    return create_error_response(
        error="Forbidden",
        error_code="FORBIDDEN",
        detail=detail,
        request_id=request_id,
        status_code=403,
    )
