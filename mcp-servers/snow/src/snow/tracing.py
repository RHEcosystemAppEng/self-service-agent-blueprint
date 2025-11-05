"""Tracing utilities for MCP tools."""

import functools
import logging
from typing import Any, Callable, TypeVar, cast

from opentelemetry import context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace.status import Status, StatusCode
from tracing_config.auto_tracing import tracingIsActive

logger = logging.getLogger()

F = TypeVar("F", bound=Callable[..., Any])


def _extract_context_from_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Extract OpenTelemetry context from request headers.

    This function looks for a Context object in the function arguments,
    extracts HTTP headers from it, and uses the global propagator to
    extract the tracing context.

    Args:
        args: Positional arguments passed to the decorated function
        kwargs: Keyword arguments passed to the decorated function

    Returns:
        Extracted context if found, otherwise the current context
    """
    # Try to find the Context object in arguments
    ctx = None

    # Check kwargs first
    if "ctx" in kwargs:
        ctx = kwargs["ctx"]
    else:
        # Check positional args for Context object
        for arg in args:
            # Check if it has request_context attribute (duck typing for Context)
            if hasattr(arg, "request_context"):
                ctx = arg
                break

    # If no context found, return current context
    if ctx is None:
        return context.get_current()

    # Try to extract headers from the context
    try:
        request_context = ctx.request_context
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                headers = request.headers
                # Convert headers to dict-like format expected by propagator
                # Normalize header keys to lowercase as traceparent is case-insensitive
                carrier = {k.lower(): v for k, v in dict(headers).items()}

                logger.debug(
                    f"Extracting tracing context from headers: {list(carrier.keys())}"
                )

                # Check for traceparent header specifically
                if "traceparent" in carrier:
                    logger.debug(f"Found traceparent header: {carrier['traceparent']}")
                else:
                    logger.debug("No traceparent header found")

                # Extract context from headers using the global propagator
                extracted_context = extract(carrier)

                # Verify if we got a valid span context
                span = trace.get_current_span(extracted_context)
                if span and span.get_span_context().is_valid:
                    logger.debug(
                        f"Successfully extracted parent span context: trace_id={span.get_span_context().trace_id}"
                    )
                else:
                    logger.debug("No valid parent span context found in headers")

                return extracted_context
    except Exception as e:
        # If extraction fails, return current context
        logger.debug(f"Failed to extract context from request: {e}")
        pass

    return context.get_current()


def trace_mcp_tool(tool_name: str | None = None) -> Callable[[F], F]:
    """Decorator to trace MCP tool calls with OpenTelemetry.

    This decorator creates a span for each MCP tool call and ensures that
    the tracing context is propagated to child operations like HTTP requests
    made by HTTPXClientInstrumentor.

    Args:
        tool_name: Optional name for the tool. If not provided, uses the function name.

    Returns:
        Decorated function with tracing enabled

    Example:
        @trace_mcp_tool()
        def my_tool(param1: str, param2: int) -> str:
            # Tool implementation
            return "result"
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Skip tracing if not active
            if not tracingIsActive():
                return func(*args, **kwargs)

            # Extract tracing context from incoming request headers
            parent_context = _extract_context_from_request(args, kwargs)

            # Get the tracer
            tracer = trace.get_tracer(__name__)

            # Use provided tool name or function name
            span_name = tool_name or f"mcp.tool.{func.__name__}"

            logger.debug(f"Starting span '{span_name}' with context: {parent_context}")

            # Start a new span for this tool call with the extracted parent context
            with tracer.start_as_current_span(
                span_name, context=parent_context
            ) as span:
                logger.debug(
                    f"Created span with trace_id={span.get_span_context().trace_id}, span_id={span.get_span_context().span_id}"
                )
                try:
                    # Add tool metadata as span attributes
                    span.set_attribute("mcp.tool.name", func.__name__)

                    # Add function parameters as attributes (excluding sensitive data)
                    for i, arg in enumerate(args):
                        # Skip Context objects and other non-primitive types
                        if not isinstance(arg, (str, int, float, bool)):
                            continue
                        span.set_attribute(f"mcp.tool.arg.{i}", str(arg))

                    for key, value in kwargs.items():
                        # Skip Context objects and other non-primitive types
                        if not isinstance(value, (str, int, float, bool)):
                            continue
                        span.set_attribute(f"mcp.tool.param.{key}", str(value))

                    # Execute the tool function
                    # The span context will automatically propagate to any
                    # instrumented HTTP calls made within this function
                    result = func(*args, **kwargs)

                    # Mark span as successful
                    span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    # Record the exception and set error status
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return cast(F, wrapper)

    return decorator
