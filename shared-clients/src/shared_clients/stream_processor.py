"""Shared streaming utilities for LlamaStack stream processing."""

import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, Optional

import structlog
from fastapi.responses import StreamingResponse

logger = structlog.get_logger()


class LlamaStackStreamProcessor:
    """Unified stream processor for LlamaStack streaming responses."""

    @staticmethod
    def _extract_token_usage(usage_object: Any) -> tuple[int, int, int]:
        """Extract token usage from a usage object. Returns (input_tokens, output_tokens, total_tokens)."""
        if not usage_object:
            return (0, 0, 0)

        # Try to get from usage object first
        input_tokens = getattr(usage_object, "prompt_tokens", 0) or getattr(
            usage_object, "input_tokens", 0
        )
        output_tokens = getattr(usage_object, "completion_tokens", 0) or getattr(
            usage_object, "output_tokens", 0
        )
        total_tokens = getattr(usage_object, "total_tokens", 0) or (
            input_tokens + output_tokens
        )

        # If no tokens found and object has direct attributes, try those
        if input_tokens == 0 and output_tokens == 0:
            if hasattr(usage_object, "input_tokens") and hasattr(
                usage_object, "output_tokens"
            ):
                input_tokens = usage_object.input_tokens or 0
                output_tokens = usage_object.output_tokens or 0
                total_tokens = input_tokens + output_tokens

        return (input_tokens, output_tokens, total_tokens)

    @staticmethod
    async def process_stream(
        response_stream: Any,
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
        metadata: dict[str, Any] = {}
        stop_reason = None
        # Token usage tracking
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        final_response = None

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
                            # Store the final response object for token extraction
                            final_response = event_payload.turn
                            if hasattr(event_payload, "turn") and hasattr(
                                event_payload.turn, "output_message"
                            ):
                                stop_reason = (
                                    event_payload.turn.output_message.stop_reason
                                )

                                # Extract token usage information
                                usage = getattr(event_payload.turn, "usage", None)
                                if usage:
                                    input_tokens, output_tokens, total_tokens = (
                                        LlamaStackStreamProcessor._extract_token_usage(
                                            usage
                                        )
                                    )
                                    logger.debug(
                                        "Extracted token usage from turn_complete",
                                        input_tokens=input_tokens,
                                        output_tokens=output_tokens,
                                        total_tokens=total_tokens,
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

        # Try to extract token usage from final response object if not found in streaming
        if (input_tokens == 0 and output_tokens == 0) and final_response:
            logger.debug(
                "No token usage found in streaming, trying final response object",
            )

            # Try to extract token usage from final response object
            usage = getattr(final_response, "usage", None)
            if usage:
                input_tokens, output_tokens, total_tokens = (
                    LlamaStackStreamProcessor._extract_token_usage(usage)
                )
                logger.debug(
                    "Extracted token usage from final response object",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
            else:
                # Try extracting from final_response directly
                input_tokens, output_tokens, total_tokens = (
                    LlamaStackStreamProcessor._extract_token_usage(final_response)
                )
                logger.debug(
                    "Extracted token usage from final response object (direct attributes)",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )

        return {
            "content": content,
            "tool_calls_made": tool_calls_made,
            "errors": errors,
            "chunk_count": chunk_count,
            "agent_id": agent_id,
            "processing_time_ms": processing_time_ms,
            "metadata": metadata,
            "stop_reason": stop_reason,
            "token_usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "final_response": final_response,
        }

    @staticmethod
    def create_stream_config(
        chunk_size: int | None = None,
        stream_delay: float | None = None,
        enable_streaming: bool = True,
    ) -> Dict[str, Any]:
        """Create standardized stream configuration with adaptive defaults."""
        return {
            "chunk_size": chunk_size,  # Will use adaptive sizing
            "stream_delay": stream_delay,  # Will use adaptive delay
            "enable_streaming": enable_streaming,
        }

    @staticmethod
    def get_optimal_stream_config(content_length: int) -> Dict[str, Any]:
        """Get optimal streaming configuration based on content length."""
        if content_length < 200:
            return {"chunk_size": 50, "stream_delay": 0.001}  # Fast for short content
        elif content_length < 1000:
            return {"chunk_size": 100, "stream_delay": 0.001}  # Balanced
        else:
            return {
                "chunk_size": 200,
                "stream_delay": 0.0005,
            }  # Optimized for long content

    @staticmethod
    async def stream_content_optimized(
        content: str, content_type: str = "content", **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """Optimized streaming with adaptive performance based on content."""
        import json

        # Get optimal configuration based on content length
        config = LlamaStackStreamProcessor.get_optimal_stream_config(len(content))
        chunk_size = config["chunk_size"]
        stream_delay = config["stream_delay"]

        logger.debug(
            "Optimized streaming configuration",
            content_length=len(content),
            chunk_size=chunk_size,
            stream_delay=stream_delay,
        )

        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            yield f"data: {json.dumps({'type': content_type, 'chunk': chunk})}\n\n"
            await asyncio.sleep(stream_delay)

    @staticmethod
    def create_sse_response(generator: Any, **kwargs: Any) -> StreamingResponse:
        """Create a standardized SSE StreamingResponse."""

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
