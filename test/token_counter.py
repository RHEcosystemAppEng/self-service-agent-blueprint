#!/usr/bin/env python3
"""
Token Counter Utility for Test Scripts

Provides thread-safe token counting for LLM calls in test scripts.
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TokenUsage:
    """Token usage data for a single LLM call"""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: Optional[str] = None
    context: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
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

    def add_usage(self, usage: TokenUsage):
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

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
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
    ):
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
                return self._context_stats.get(context, TokenStats())
            else:
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

    def reset(self, context: Optional[str] = None):
        """Reset token counts, optionally for a specific context"""
        with self._stats_lock:
            if context:
                if context in self._context_stats:
                    del self._context_stats[context]
            else:
                self._stats = TokenStats()
                self._context_stats.clear()

    def print_summary(self, context: Optional[str] = None, prefix: str = ""):
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


def count_tokens_from_response(
    response, model: Optional[str] = None, context: Optional[str] = None
):
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
        except AttributeError as e:
            # Handle cases where attributes don't exist or are inaccessible
            print(f"Warning: Could not access token attributes: {e}")

        # If direct token access failed, try content estimation
        if input_tokens == 0 and output_tokens == 0:
            # Try to estimate tokens from content length
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
                    # Rough estimation: 1 token ~= 4 characters
                    output_tokens = max(1, len(content) // 4)
                    input_tokens = 50  # Rough estimate for prompts
            except Exception:
                pass

        if input_tokens > 0 or output_tokens > 0:
            counter = TokenCounter()
            counter.add_tokens(input_tokens, output_tokens, model, context)

        return input_tokens, output_tokens
    except Exception:
        return 0, 0


# Global convenience functions
def add_tokens(
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None,
    context: Optional[str] = None,
):
    """Global function to add tokens to the counter"""
    counter = TokenCounter()
    counter.add_tokens(input_tokens, output_tokens, model, context)


def get_token_stats(context: Optional[str] = None) -> TokenStats:
    """Global function to get token statistics"""
    counter = TokenCounter()
    return counter.get_stats(context)


def print_token_summary(context: Optional[str] = None, prefix: str = ""):
    """Global function to print token summary"""
    counter = TokenCounter()
    counter.print_summary(context, prefix)


def reset_tokens(context: Optional[str] = None):
    """Global function to reset token counts"""
    counter = TokenCounter()
    counter.reset(context)
