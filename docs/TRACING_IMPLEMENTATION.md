# Distributed Tracing Implementation

This document describes the distributed tracing implementation across the self-service agent system, with a focus on end-to-end context propagation from client to MCP tools.

## Architecture Overview

The tracing flow covers three main components:

```
Client → Agent Service → Llama Stack → MCP Server (e.g., Snow MCP)
```

## Complete Tracing Flow

### 1. Client → Agent Service

**Status:** ✅ Automatic (via FastAPIInstrumentor)

The Agent Service uses FastAPI with OpenTelemetry instrumentation:
- Incoming requests automatically create root spans
- Request headers are parsed for existing trace context
- HTTP context propagation is handled automatically

**Location:** `agent-service/src/agent_service/main.py`
```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
auto_tracing_run(SERVICE_NAME, logger)
```

### 2. Agent Service → Llama Stack

**Status:** ✅ Automatic (via HTTPXClientInstrumentor)

The Agent Service uses httpx-based clients (OpenAI SDK and LlamaStackClient):
- HTTPXClientInstrumentor automatically traces outgoing HTTP requests
- Tracing context is propagated in HTTP headers to Llama Stack
- Child spans are created for each HTTP call

**Location:** `tracing-config/src/tracing_config/auto_tracing.py`
```python
HTTPXClientInstrumentor().instrument()
set_global_textmap(TraceContextTextMapPropagator())
```

### 3. Llama Stack → MCP Server

**Status:** ✅ Manual injection (configured in tool headers)

When the Agent Service configures MCP tools for Llama Stack, it injects the current tracing context into the tool headers:

**Location:** `agent-service/src/agent_service/langgraph/responses_agent.py`

```python
# Build headers dictionary
headers: Dict[str, str] = {}

# Add authoritative_user_id if provided
if authoritative_user_id:
    headers["AUTHORITATIVE_USER_ID"] = authoritative_user_id

# Add tracing headers if tracing is active
if tracingIsActive():
    # Inject current tracing context into headers
    # This will add traceparent and tracestate headers
    inject(headers)
    logger.debug(f"Injected tracing headers for MCP server {server_name}: {list(headers.keys())}")

# Only add headers dict if it's not empty
if headers:
    mcp_tool["headers"] = headers
```

**What happens:**
1. When an MCP tool is configured, the current OpenTelemetry context is extracted
2. `inject(headers)` adds `traceparent` and `tracestate` to the headers dict
3. These headers are passed to Llama Stack as part of the MCP tool configuration
4. When Llama Stack invokes the MCP tool, it includes these headers in the HTTP request
5. The MCP server's `@trace_mcp_tool()` decorator extracts the parent context

### 4. MCP Tool Execution

**Status:** ✅ Manual (via @trace_mcp_tool decorator)

MCP tools use a custom decorator to create spans and extract parent context:

**Location:** `mcp-servers/snow/src/snow/tracing.py`

```python
@mcp.tool()
@trace_mcp_tool()
def open_laptop_refresh_ticket(...):
    # Tool implementation
```

**The decorator:**
1. Extracts tracing headers from the incoming MCP request
2. Uses `extract(carrier)` to rebuild the parent span context
3. Creates a new span as a child of the extracted context
4. Sets the span as current context for downstream operations
5. Any HTTP calls within the tool (e.g., to ServiceNow) become child spans via HTTPXClientInstrumentor

## Example Trace Hierarchy

When a complete request flows through the system, you'll see:

```
http.request /api/chat (agent-service)                    [trace_id: abc123]
  └─ httpx.client POST http://llamastack:8321/responses    [trace_id: abc123]
      └─ mcp.tool.open_laptop_refresh_ticket               [trace_id: abc123]
          └─ httpx.client POST https://servicenow.com/...  [trace_id: abc123]
```

All spans share the same `trace_id`, creating a complete distributed trace.

## Accessing and Viewing Traces

Once tracing is enabled and traces are being exported, you can view them using Jaeger or any other OTLP-compatible tracing UI.

### Using Jaeger

Jaeger is the default distributed tracing UI used in this system. To access traces:

1. **Access the Jaeger UI**: Navigate to your Jaeger instance (typically running on port 16686)
   - Local development: `http://localhost:16686`
   - OpenShift: Access via the Jaeger route in your namespace

2. **Find Traces**: In the Jaeger UI:
   - Select the service from the dropdown (e.g., `agent-service`, `snow-mcp`)
   - Filter by operation (e.g., `/api/chat`, `open_laptop_refresh_ticket`)
   - Set time range to find recent traces
   - Click "Find Traces" to search

3. **View Trace Details**: Click on any trace to see:
   - Complete request flow across all services
   - Timing breakdown for each span
   - HTTP headers and metadata
   - Error details if any span failed
   - The complete distributed context with shared `trace_id`

4. **Analyze Performance**:
   - Identify slow operations by comparing span durations
   - Find bottlenecks in the request path
   - Track how long tool calls take vs LLM processing
   - See the complete latency breakdown from client to backend systems

### Alternative Trace Viewers

The system uses OpenTelemetry with OTLP export, making it compatible with various tracing backends:

- **Jaeger**: Default UI, excellent for distributed tracing visualization
- **Grafana Tempo**: For integrated observability with metrics and logs
- **OpenTelemetry Collector**: Can export to multiple backends simultaneously
- **OpenShift Console**: Built-in observability features in OpenShift environments

All trace viewers that support OTLP can consume the traces from this system without code changes.

## Configuration

### Enable Tracing

Set the OTLP exporter endpoint:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://your-otel-collector:4318"
```

### Debug Logging

To see tracing-related debug information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or via environment variable:

```bash
export OTEL_LOG_LEVEL=debug
```

### Verify Tracing

When tracing is working correctly, you should see log messages like:

```
DEBUG - Injected tracing headers for MCP server snow-server: ['AUTHORITATIVE_USER_ID', 'traceparent', 'tracestate']
DEBUG - Extracting tracing context from headers: ['host', 'user-agent', 'traceparent', 'tracestate', ...]
DEBUG - Found traceparent header: 00-abc123...
DEBUG - Successfully extracted parent span context: trace_id=abc123...
DEBUG - Created span with trace_id=abc123, span_id=def456
```

## Key Implementation Details

### Header Normalization

MCP tracing decorator normalizes header keys to lowercase:

```python
carrier = {k.lower(): v for k, v in dict(headers).items()}
```

This ensures the `traceparent` header is found regardless of case variations.

### Context Extraction

The MCP decorator extracts context from the FastMCP Context object:

```python
def _extract_context_from_request(args, kwargs):
    # Find Context object in arguments
    # Extract HTTP headers
    # Use global propagator to extract parent context
    return extract(carrier)
```

### Zero Overhead When Disabled

All tracing code checks if tracing is active:

```python
if not tracingIsActive():
    return func(*args, **kwargs)
```

When `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, tracing has minimal performance impact.

## Trace Attributes

### MCP Tool Spans

Each MCP tool span includes:
- `mcp.tool.name`: Function name
- `mcp.tool.arg.{i}`: Positional arguments (primitive types only)
- `mcp.tool.param.{key}`: Keyword arguments (primitive types only)

### HTTP Spans

HTTPXClientInstrumentor automatically adds:
- `http.method`: HTTP method (GET, POST, etc.)
- `http.url`: Full URL
- `http.status_code`: Response status code
- `http.request.header.*`: Request headers
- `http.response.header.*`: Response headers

## Troubleshooting

### Spans are created but not linked

**Symptom:** You see spans in your traces but they have different trace IDs.

**Cause:** Tracing context is not being propagated between services.

**Solution:** Check debug logs to see if:
- Tracing headers are being injected: Look for "Injected tracing headers"
- Tracing headers are being received: Look for "Extracting tracing context from headers"
- Parent context is being extracted: Look for "Successfully extracted parent span context"

### No tracing headers in MCP requests

**Symptom:** Debug logs show "No traceparent header found"

**Cause:** The tracing context may not be active when MCP tools are configured.

**Solution:** Ensure that `_get_mcp_tools_to_use()` is called within an active span context. The method is typically called during agent response processing, which should already have an active span.

### Different trace IDs for each service

**Symptom:** Each service starts a new trace instead of continuing the existing one.

**Cause:** The global propagator may not be configured correctly.

**Solution:** Verify that `set_global_textmap(TraceContextTextMapPropagator())` is called during initialization in `auto_tracing.run()`.

## Future Improvements

1. **Async span creation**: Update decorator to handle async functions
2. **Span events**: Add events for key operations (e.g., shield checks, tool approvals)
3. **Baggage propagation**: Propagate additional metadata via OpenTelemetry Baggage API
4. **Metrics integration**: Add metrics for trace sampling, span counts, etc.
5. **Llama Stack instrumentation**: Contribute OpenTelemetry instrumentation to Llama Stack project

## References

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/languages/python/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry HTTPX Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html)
- [FastAPI Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)

