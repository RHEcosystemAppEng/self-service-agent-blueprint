"""Shared MCP request header helpers (HTTP context, case-insensitive lookup)."""

from collections.abc import Mapping
from typing import Any, cast

from mcp.server.fastmcp import Context
from shared_models import configure_logging

logger = configure_logging(__name__)


def mcp_http_headers(ctx: Context[Any, Any]) -> Mapping[str, Any] | None:
    """Return HTTP headers from a FastMCP ``Context`` (streamable-http), or ``None``."""
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                return request.headers
    except Exception as e:
        logger.debug(
            "Error reading MCP HTTP headers from context",
            error=str(e),
            error_type=type(e).__name__,
        )
    return None


def header_first(ctx: Context[Any, Any], *names: str) -> str | None:
    """First header value among ``names`` (Starlette-style case-insensitive lookup)."""
    headers = mcp_http_headers(ctx)
    if headers is None:
        return None
    for name in names:
        value = headers.get(name)
        if value is not None:
            return cast(str, str(value))
    return None
