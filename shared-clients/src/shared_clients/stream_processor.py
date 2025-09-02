"""Shared streaming utilities for LlamaStack stream processing."""

import asyncio
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger()


class LlamaStackStreamProcessor:
    """Unified stream processor for LlamaStack streaming responses."""

    @staticmethod
    async def process_stream(
        response_stream,
        on_content: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str], None]] = None,
        collect_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Process a LlamaStack streaming response with unified logic.

        Args:
            response_stream: The streaming response from LlamaStack
            on_content: Optional callback for content chunks
            on_error: Optional callback for errors
            on_tool_call: Optional callback for tool calls
            collect_content: Whether to collect and return the full content

        Returns:
            Dict containing the processed response data
        """
        content = ""
        chunk_count = 0
        tool_calls_made = []
        errors = []
        agent_id = None
        processing_time_ms = None
        metadata = {}
        stop_reason = None

        try:
            for chunk in response_stream:
                chunk_count += 1
                logger.debug(
                    "Processing stream chunk",
                    chunk_type=type(chunk).__name__,
                    chunk_count=chunk_count,
                )

                # Handle errors
                if hasattr(chunk, "error") and chunk.error:
                    error_message = chunk.error.get("message", "Unknown agent error")
                    errors.append(error_message)
                    logger.error("Stream error", error=error_message)
                    if on_error:
                        on_error(error_message)
                    continue

                # Process events
                if hasattr(chunk, "event"):
                    try:
                        # Handle different event structures
                        if hasattr(chunk.event, "payload"):
                            # Old structure: chunk.event.payload
                            event_payload = chunk.event.payload
                        elif hasattr(chunk.event, "event_type"):
                            # New structure: chunk.event directly
                            event_payload = chunk.event
                        else:
                            logger.warning(
                                "Unknown event structure",
                                event_attrs=dir(chunk.event),
                                chunk_count=chunk_count,
                            )
                            continue

                        # Track tool calls
                        if (
                            hasattr(event_payload, "event_type")
                            and event_payload.event_type == "tool_call"
                        ):
                            tool_name = getattr(event_payload, "tool_name", "unknown")
                            tool_calls_made.append(tool_name)
                            logger.debug("Tool called", tool_name=tool_name)
                            if on_tool_call:
                                on_tool_call(tool_name)

                        # Handle turn completion
                        if (
                            hasattr(event_payload, "event_type")
                            and event_payload.event_type == "turn_complete"
                        ):
                            if hasattr(event_payload, "turn") and hasattr(
                                event_payload.turn, "output_message"
                            ):
                                stop_reason = (
                                    event_payload.turn.output_message.stop_reason
                                )

                                if stop_reason == "end_of_turn":
                                    chunk_content = (
                                        event_payload.turn.output_message.content
                                    )
                                    content += chunk_content
                                    logger.debug(
                                        "Extracted content from turn_complete",
                                        content_length=len(chunk_content),
                                        chunk_count=chunk_count,
                                    )
                                    if on_content:
                                        on_content(chunk_content)
                                else:
                                    # Handle other stop reasons
                                    stop_message = f"[Agent stopped: {stop_reason}]"
                                    content += stop_message
                                    logger.info(
                                        "Agent stopped with reason",
                                        stop_reason=stop_reason,
                                        chunk_count=chunk_count,
                                    )
                                    if on_content:
                                        on_content(stop_message)

                    except Exception as e:
                        logger.error(
                            "Error processing event",
                            error=str(e),
                            chunk_count=chunk_count,
                        )
                        errors.append(str(e))
                        if on_error:
                            on_error(str(e))

        except Exception as e:
            logger.error("Error in stream processing", error=str(e))
            errors.append(str(e))
            if on_error:
                on_error(str(e))

        return {
            "content": content,
            "tool_calls_made": tool_calls_made,
            "errors": errors,
            "chunk_count": chunk_count,
            "agent_id": agent_id,
            "processing_time_ms": processing_time_ms,
            "metadata": metadata,
            "stop_reason": stop_reason,
        }

    @staticmethod
    def create_stream_config(
        chunk_size: int = 50,
        stream_delay: float = 0.01,
        enable_streaming: bool = True,
    ) -> Dict[str, Any]:
        """Create standardized stream configuration."""
        return {
            "chunk_size": chunk_size,
            "stream_delay": stream_delay,
            "enable_streaming": enable_streaming,
        }

    @staticmethod
    async def stream_content_to_sse(
        content: str,
        chunk_size: int = 50,
        stream_delay: float = 0.01,
    ):
        """Stream content as Server-Sent Events."""
        import json

        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'content', 'chunk': chunk})}\n\n"
            await asyncio.sleep(stream_delay)

    @staticmethod
    def create_sse_response(generator, **kwargs):
        """Create a standardized SSE StreamingResponse."""
        from fastapi.responses import StreamingResponse

        default_headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }

        headers = {**default_headers, **kwargs.get("headers", {})}

        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers=headers,
        )

    @staticmethod
    def create_sse_start_event(request_id: str) -> str:
        """Create a standardized SSE start event."""
        import json

        return f"data: {json.dumps({'type': 'start', 'request_id': request_id})}\n\n"

    @staticmethod
    def create_sse_complete_event(agent_id: str, processing_time_ms: int) -> str:
        """Create a standardized SSE complete event."""
        import json

        return f"data: {json.dumps({'type': 'complete', 'agent_id': agent_id, 'processing_time_ms': processing_time_ms})}\n\n"

    @staticmethod
    def create_sse_error_event(message: str) -> str:
        """Create a standardized SSE error event."""
        import json

        return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
