import os
import typing

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"


def tracingIsActive() -> bool:
    return bool(os.environ.get(OTEL_EXPORTER_OTLP_ENDPOINT))


def run(service_name: str, logger: typing.Any) -> None:
    otel_exporter_endpoint = os.environ.get(OTEL_EXPORTER_OTLP_ENDPOINT)
    if not otel_exporter_endpoint:
        logger.info("OTEL exporter endpoint not provided -- skip auto tracing config.")
        return

    logger.info(f"Export tracing to {otel_exporter_endpoint}")
    # Set up the tracer provider with service name
    resource = Resource(attributes={service_attributes.SERVICE_NAME: service_name})
    trace.set_tracer_provider(TracerProvider(resource=resource))

    # Set up the OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{otel_exporter_endpoint}/v1/traces",
    )

    # Set up the span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)  # type: ignore[attr-defined]

    # Set up instrumentations
    HTTPXClientInstrumentor().instrument()

    # Set up propagator
    set_global_textmap(TraceContextTextMapPropagator())
