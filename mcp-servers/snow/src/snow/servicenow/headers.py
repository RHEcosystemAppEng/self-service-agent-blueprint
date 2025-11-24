"""Header extraction utilities for ServiceNow MCP server."""

from typing import Any

from mcp.server.fastmcp import Context
from shared_models import configure_logging

logger = configure_logging(__name__)


def extract_authoritative_user_id(ctx: Context[Any, Any]) -> str | None:
    """Extract authoritative user ID from request context headers.

    Args:
        ctx: Request context containing headers

    Returns:
        Authoritative user ID if found, None otherwise
    """
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers
                user_id = headers.get("AUTHORITATIVE_USER_ID") or headers.get(
                    "authoritative_user_id"
                )
                return str(user_id) if user_id is not None else None
    except Exception as e:
        logger.debug(
            "Error extracting headers from request context",
            error=str(e),
            error_type=type(e).__name__,
        )

    return None


def extract_servicenow_token(ctx: Context[Any, Any]) -> str | None:
    """Extract ServiceNow API token from request context headers.

    This implements pass-through authentication where the client (agent-service)
    reads the API key from its environment and passes it via the X-ServiceNow-Token header.

    Args:
        ctx: Request context containing headers

    Returns:
        ServiceNow API token if found, None otherwise
    """
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers
                # Check both uppercase and lowercase variants
                token = headers.get("SERVICE_NOW_TOKEN")
                return str(token) if token is not None else None
    except Exception as e:
        logger.debug(
            "Error extracting ServiceNow token from request context", error=str(e)
        )

    return None
