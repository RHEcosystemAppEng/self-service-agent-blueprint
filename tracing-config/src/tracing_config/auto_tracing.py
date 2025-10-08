import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def run():
    otel_exporter_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otel_exporter_endpoint:
        return

    # Set up the tracer provider
    trace.set_tracer_provider(TracerProvider())

    # Set up the OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{otel_exporter_endpoint}/v1/traces",
    )

    # Set up the span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

    # Set up instrumentations
    HTTPXClientInstrumentor().instrument()

    # Set up propagator
    set_global_textmap(TraceContextTextMapPropagator())
