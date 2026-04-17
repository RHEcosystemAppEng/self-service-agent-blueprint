"""OpenTelemetry tracing for MCP tools (shared by Snow, Zammad, etc.)."""

import functools
from typing import Any, Callable, ParamSpec, TypeVar, cast

from mcp_common.headers import mcp_http_headers
from opentelemetry import context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace.status import Status, StatusCode
from shared_models import configure_logging
from tracing_config.auto_tracing import tracingIsActive

logger = configure_logging(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _extract_context_from_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    ctx = None
    if "ctx" in kwargs:
        ctx = kwargs["ctx"]
    else:
        for arg in args:
            if hasattr(arg, "request_context"):
                ctx = arg
                break

    if ctx is None:
        return context.get_current()

    try:
        headers = mcp_http_headers(ctx)
        if headers is not None:
            carrier = {k.lower(): v for k, v in dict(headers).items()}
            logger.debug(
                "Extracting tracing context from headers",
                headers=list(carrier.keys()),
            )
            extracted_context = extract(carrier)
            span = trace.get_current_span(extracted_context)
            if span and span.get_span_context().is_valid:
                logger.debug(
                    "Successfully extracted parent span context",
                    trace_id=span.get_span_context().trace_id,
                )
            return extracted_context
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        logger.debug("Failed to extract context from request", error=str(e))

    return context.get_current()


def trace_mcp_tool(
    tool_name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to trace MCP tool calls with OpenTelemetry."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not tracingIsActive():
                return func(*args, **kwargs)

            parent_context = _extract_context_from_request(
                cast(tuple[Any, ...], args), cast(dict[str, Any], kwargs)
            )
            tracer = trace.get_tracer(__name__)
            span_name = tool_name or f"mcp.tool.{func.__name__}"

            logger.debug(
                "Starting span", span_name=span_name, context=str(parent_context)
            )

            with tracer.start_as_current_span(
                span_name, context=parent_context
            ) as span:
                logger.debug(
                    "Created span",
                    trace_id=span.get_span_context().trace_id,
                    span_id=span.get_span_context().span_id,
                )
                try:
                    span.set_attribute("mcp.tool.name", func.__name__)
                    for i, arg in enumerate(args):
                        if not isinstance(arg, (str, int, float, bool)):
                            continue
                        span.set_attribute(f"mcp.tool.arg.{i}", str(arg))
                    for key, value in kwargs.items():
                        if not isinstance(value, (str, int, float, bool)):
                            continue
                        span.set_attribute(f"mcp.tool.param.{key}", str(value))
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except BaseException as e:
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator
