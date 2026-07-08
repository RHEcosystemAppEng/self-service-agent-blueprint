#!/usr/bin/env python3
import contextlib
import json
import os
from collections.abc import AsyncIterator
from typing import Any, Optional

from shared_models import configure_logging

logger = configure_logging("agent-service")


def mlflowIsActive() -> bool:
    return os.getenv("MLFLOW_ENABLED", "false").lower() == "true"


def configure_mlflow() -> bool:
    """Configure MLflow tracing at process startup. Call once from main.py.

    Sets the tracking URI and experiment. If MLFLOW_TRACKING_TOKEN is not set,
    attempts to read the projected ServiceAccount token for RHOAI OAuth.
    Returns True if successfully configured.
    """
    if not mlflowIsActive():
        return False

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        logger.warning("MLFLOW_TRACKING_URI not set — MLflow tracking disabled")
        return False

    if not os.getenv("MLFLOW_TRACKING_TOKEN"):
        sa_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        try:
            with open(sa_token_path) as fh:
                os.environ["MLFLOW_TRACKING_TOKEN"] = fh.read().strip()
        except (FileNotFoundError, PermissionError):
            pass

    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)

        namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        try:
            with open(namespace_path) as fh:
                namespace = fh.read().strip()
            mlflow.set_workspace(namespace)
        except (FileNotFoundError, PermissionError):
            namespace = None

        experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "self-service-agent")
        mlflow.set_experiment(experiment_name)
        logger.info(
            "MLflow tracing configured",
            tracking_uri=tracking_uri,
            workspace=namespace,
            experiment=experiment_name,
        )
        return True
    except Exception as e:
        logger.error("Failed to configure MLflow tracing", error=str(e))
        return False


@contextlib.asynccontextmanager
async def mlflow_turn_span(
    thread_id: str,
    agent_name: Optional[str],
    user_id: Optional[str],
) -> AsyncIterator[Optional[Any]]:
    """Async context manager wrapping one conversation turn.

    Yields the active span (or None on setup failure) so the caller can set
    the user message as inputs and the agent response as outputs:

        async with mlflow_turn_span(...) as span:
            if span:
                span.set_inputs({"message": user_message})
            response = await _send_message_impl(...)
            if span:
                span.set_outputs({"response": response})

    Child LLM spans created by trace_llm_call() nest automatically under this
    span via MLflow's ContextVar propagation. mlflow.trace.session metadata
    drives the Sessions view in the MLflow UI.
    """
    if not mlflowIsActive():
        yield None
        return

    # mlflow.start_span() is a synchronous context manager; ExitStack lets us
    # register it for deferred cleanup so its __exit__ fires after the yield.
    # Without this, a plain `with mlflow.start_span():` inside an
    # @asynccontextmanager would close the span before the caller's body runs.
    # ExitStack also ensures we always reach the yield even when span creation
    # raises, satisfying @asynccontextmanager's single-yield requirement.
    with contextlib.ExitStack() as stack:
        active_span = None
        try:
            import mlflow
            from mlflow.entities import SpanType

            active_span = stack.enter_context(
                mlflow.start_span("Turn", span_type=SpanType.AGENT)
            )

            # Reserved metadata keys drive specific MLflow UI features:
            # mlflow.trace.session → Sessions view grouping
            # mlflow.trace.user   → User column in both Traces and Sessions views
            metadata: dict[str, str] = {"mlflow.trace.session": thread_id}
            if user_id:
                metadata["mlflow.trace.user"] = user_id
            # Tags appear as filterable columns in the Traces view.
            # session_id and user_id are duplicated here so they surface in
            # Traces view tag columns in addition to their metadata roles.
            tags: dict[str, str] = {"session_id": thread_id}
            if user_id:
                tags["user_id"] = user_id
            if agent_name:
                tags["agent_name"] = agent_name
            mlflow.update_current_trace(metadata=metadata, tags=tags)
        except Exception as e:
            logger.warning("MLflow turn span setup failed", error=str(e))

        yield active_span


def trace_llm_call(
    messages: list[Any],
    model: str,
    temperature: float,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    response: "Any" = None,
    response_text: Optional[str] = None,
    error: Optional[Exception] = None,
) -> None:
    """Create a child CHAT_MODEL span under the active turn span.

    Pass response (the full Responses API object) on success so tool calls and
    all intermediate output items are visible in the MLflow UI — mirroring what
    mlflow.openai.autolog() captures. Falls back to response_text if response
    is not provided. Pass error on failure to mark the span as errored.

    No-ops silently if MLflow is disabled or there is no active span.
    """
    if not mlflowIsActive():
        return

    try:
        import mlflow
        from mlflow.entities import SpanType
        from mlflow.entities.span_event import SpanEvent
        from mlflow.entities.span_status import SpanStatusCode

        with mlflow.start_span("Responses", span_type=SpanType.CHAT_MODEL) as span:
            # MESSAGE_FORMAT = "mlflow.message.format": tells the UI to render the Chat tab
            span.set_attribute("mlflow.message.format", "openai")
            span.set_inputs({"messages": messages})
            span.set_attribute("model", model or "")
            span.set_attribute("temperature", float(temperature or 0))
            # CHAT_USAGE = "mlflow.chat.tokenUsage": drives the token-usage display in the UI
            span.set_attribute(
                "mlflow.chat.tokenUsage",
                {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )
            span.set_attribute("latency_ms", latency_ms)
            if error is not None:
                span.add_event(SpanEvent.from_exception(error))
                span.set_status(SpanStatusCode.ERROR)
            else:
                # Use the full response object so tool calls in response.output
                # are visible, falling back to the extracted text string.
                span.set_outputs(
                    response
                    if response is not None
                    else {"content": response_text or ""}
                )
                # mlflow.trace.tokenUsage at trace level drives the Tokens column
                # in the Traces and Sessions views.
                mlflow.update_current_trace(
                    metadata={
                        "mlflow.trace.tokenUsage": json.dumps(
                            {
                                "input_tokens": prompt_tokens,
                                "output_tokens": completion_tokens,
                                "total_tokens": prompt_tokens + completion_tokens,
                            }
                        )
                    }
                )
    except Exception as e:
        logger.warning("MLflow LLM span failed", error=str(e))
