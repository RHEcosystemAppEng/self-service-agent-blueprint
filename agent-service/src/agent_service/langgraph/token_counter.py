#!/usr/bin/env python3
"""
Token Counter Utility for Agent Service

Provides thread-safe token counting for LLM calls in agent service.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TokenUsage:
    """Token usage data for a single LLM call"""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: Optional[str] = None
    context: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            import time

            self.timestamp = time.time()


@dataclass
class TokenStats:
    """Aggregate token statistics"""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_total_tokens: int = 0
    calls: List[TokenUsage] = field(default_factory=list)

    def add_usage(self, usage: TokenUsage) -> None:
        """Add a token usage record"""
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        self.call_count += 1

        # Update maximum values
        self.max_input_tokens = max(self.max_input_tokens, usage.input_tokens)
        self.max_output_tokens = max(self.max_output_tokens, usage.output_tokens)
        self.max_total_tokens = max(self.max_total_tokens, usage.total_tokens)

        self.calls.append(usage)


class TokenCounter:
    """Thread-safe global token counter"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "TokenCounter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if not getattr(self, "_initialized", False):
            self._stats_lock = threading.Lock()
            self._stats = TokenStats()
            self._context_stats: Dict[str, TokenStats] = {}
            self._initialized = True

    def add_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None,
        context: Optional[str] = None,
    ) -> None:
        """Add token usage with optional context"""
        total_tokens = input_tokens + output_tokens
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=model,
            context=context,
        )

        with self._stats_lock:
            self._stats.add_usage(usage)

            if context:
                if context not in self._context_stats:
                    self._context_stats[context] = TokenStats()
                self._context_stats[context].add_usage(usage)

    def get_stats(self, context: Optional[str] = None) -> TokenStats:
        """Get token statistics, optionally filtered by context"""
        with self._stats_lock:
            if context:
                # Return context-specific stats if they exist, otherwise empty stats
                if context in self._context_stats:
                    return self._context_stats[context]
                else:
                    return TokenStats()  # Empty stats for non-existent contexts
            else:
                # Return global stats (no context requested)
                return TokenStats(
                    total_input_tokens=self._stats.total_input_tokens,
                    total_output_tokens=self._stats.total_output_tokens,
                    total_tokens=self._stats.total_tokens,
                    call_count=self._stats.call_count,
                    max_input_tokens=self._stats.max_input_tokens,
                    max_output_tokens=self._stats.max_output_tokens,
                    max_total_tokens=self._stats.max_total_tokens,
                    calls=self._stats.calls.copy(),
                )

    def reset(self, context: Optional[str] = None) -> None:
        """Reset token counts, optionally for a specific context"""
        with self._stats_lock:
            if context:
                if context in self._context_stats:
                    del self._context_stats[context]
            else:
                self._stats = TokenStats()
                self._context_stats.clear()

    def print_summary(self, context: Optional[str] = None, prefix: str = "") -> None:
        """Print a summary of token usage"""
        stats = self.get_stats(context)

        if context:
            print(f"{prefix}Token Usage Summary for {context}:")
        else:
            print(f"{prefix}Total Token Usage Summary:")

        print(f"{prefix}  Total calls: {stats.call_count}")
        print(f"{prefix}  Input tokens: {stats.total_input_tokens:,}")
        print(f"{prefix}  Output tokens: {stats.total_output_tokens:,}")
        print(f"{prefix}  Total tokens: {stats.total_tokens:,}")

        if stats.call_count > 0:
            print(f"{prefix}  Max single request input: {stats.max_input_tokens:,}")
            print(f"{prefix}  Max single request output: {stats.max_output_tokens:,}")
            print(f"{prefix}  Max single request total: {stats.max_total_tokens:,}")

            avg_input = stats.total_input_tokens / stats.call_count
            avg_output = stats.total_output_tokens / stats.call_count
            avg_total = stats.total_tokens / stats.call_count
            print(
                f"{prefix}  Average per call: {avg_input:.1f} input, {avg_output:.1f} output, {avg_total:.1f} total"
            )


def estimate_tokens_from_text(text: str) -> int:
    """Improved token estimation from text content"""
    if not text:
        return 0

    # More sophisticated estimation accounting for common patterns
    # This is still approximate but much better than a fixed value

    # Remove extra whitespace
    cleaned_text = " ".join(text.split())
    char_count = len(cleaned_text)

    # Base estimation: ~3.5-4 characters per token for English
    # Adjust based on content patterns
    base_tokens = char_count / 3.7

    # Adjust for common patterns that affect tokenization
    # Technical terms, code, structured data tend to use more tokens
    if any(
        keyword in text.lower()
        for keyword in [
            "critical",
            "assistant:",
            "user:",
            "employee_id",
            "laptop",
            "servicenow",
        ]
    ):
        base_tokens *= 1.1  # Technical content uses slightly more tokens

    # JSON-like structures or repeated patterns
    if text.count("{") > 2 or text.count(":") > 5:
        base_tokens *= 1.15

    return max(1, int(base_tokens))


def count_tokens_from_messages(messages: list[Any]) -> int:
    """Estimate input tokens from the actual messages being sent to LLM"""
    if not messages:
        return 0

    total_tokens = 0
    for message in messages:
        if isinstance(message, dict):
            content = message.get("content", "")
            # Add small overhead for role and message structure
            total_tokens += estimate_tokens_from_text(content) + 3
        elif hasattr(message, "content"):
            total_tokens += estimate_tokens_from_text(str(message.content)) + 3
        else:
            total_tokens += estimate_tokens_from_text(str(message)) + 3

    # Add overhead for message formatting and API structure
    total_tokens += len(messages) * 2

    return total_tokens


def count_tokens_from_response(
    response: Any,
    model: Optional[str] = None,
    context: Optional[str] = None,
    input_messages: list[Any] | None = None,
) -> tuple[int, int]:
    """Extract and count tokens from a LlamaStack response object"""
    try:
        input_tokens = 0
        output_tokens = 0

        # Try to extract token information from LlamaStack response
        try:
            if hasattr(response, "usage") and response.usage is not None:
                usage = response.usage
                input_tokens = getattr(usage, "prompt_tokens", 0) or getattr(
                    usage, "input_tokens", 0
                )
                output_tokens = getattr(usage, "completion_tokens", 0) or getattr(
                    usage, "output_tokens", 0
                )
            elif hasattr(response, "input_tokens") and hasattr(
                response, "output_tokens"
            ):
                input_tokens = response.input_tokens or 0
                output_tokens = response.output_tokens or 0
        except AttributeError:
            # Handle cases where attributes don't exist or are inaccessible
            pass

        # If direct token access failed, use improved estimation
        if input_tokens == 0 and output_tokens == 0:
            # Estimate input tokens from the messages that were actually sent
            if input_messages:
                input_tokens = count_tokens_from_messages(input_messages)
            else:
                # Fallback to old behavior if messages not provided
                input_tokens = 50

            # Estimate output tokens from response content
            content = ""
            try:
                if hasattr(response, "output_text"):
                    content = response.output_text or ""
                elif hasattr(response, "output") and response.output:
                    output_msg = response.output[0]
                    if hasattr(output_msg, "content") and output_msg.content:
                        content_item = output_msg.content[0]
                        if hasattr(content_item, "text"):
                            content = content_item.text or ""

                if content:
                    output_tokens = estimate_tokens_from_text(content)
            except Exception:
                pass

        if input_tokens > 0 or output_tokens > 0:
            # Save to database if context is a session ID
            if context and context.startswith("session_"):
                # Extract session_id from context (format: "session_{session_id}")
                session_id = context[8:]  # Remove "session_" prefix

                # Schedule database save asynchronously (fire and forget)
                import asyncio

                async def _save_tokens() -> None:
                    try:
                        from shared_models.database import get_db_session
                        from shared_models.session_token_service import (
                            SessionTokenService,
                        )

                        async with get_db_session() as db:
                            await SessionTokenService.update_token_counts(
                                db, session_id, input_tokens, output_tokens
                            )
                    except Exception as e:
                        import logging

                        logging.getLogger(__name__).warning(
                            f"Failed to save token counts to database for session {session_id}: {e}"
                        )

                asyncio.create_task(_save_tokens())

        return input_tokens, output_tokens
    except Exception:
        return 0, 0


# Global convenience functions
def add_tokens(
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None,
    context: Optional[str] = None,
) -> None:
    """Global function to add tokens to the counter"""
    counter = TokenCounter()
    counter.add_tokens(input_tokens, output_tokens, model, context)


def get_token_stats(context: Optional[str] = None) -> TokenStats:
    """Global function to get token statistics"""
    counter = TokenCounter()
    return counter.get_stats(context)


def print_token_summary(context: Optional[str] = None, prefix: str = "") -> None:
    """Global function to print token summary"""
    counter = TokenCounter()
    counter.print_summary(context, prefix)


def reset_tokens(context: Optional[str] = None) -> None:
    """Global function to reset token counts"""
    counter = TokenCounter()
    counter.reset(context)
