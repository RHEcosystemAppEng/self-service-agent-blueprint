#!/usr/bin/env python3
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _TokenUsage:
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
class _TokenStats:
    """Aggregate token statistics"""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_total_tokens: int = 0
    calls: List[_TokenUsage] = field(default_factory=list)

    def add_usage(self, usage: _TokenUsage) -> None:
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
            self._stats = _TokenStats()
            self._context_stats: Dict[str, _TokenStats] = {}
            self._initialized = True

    def _add_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None,
        context: Optional[str] = None,
    ) -> None:
        """Add token usage with optional context"""
        total_tokens = input_tokens + output_tokens
        usage = _TokenUsage(
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
                    self._context_stats[context] = _TokenStats()
                self._context_stats[context].add_usage(usage)

    def _get_stats(self, context: Optional[str] = None) -> _TokenStats:
        """Get token statistics, optionally filtered by context"""
        with self._stats_lock:
            if context:
                return self._context_stats.get(context, _TokenStats())
            else:
                return _TokenStats(
                    total_input_tokens=self._stats.total_input_tokens,
                    total_output_tokens=self._stats.total_output_tokens,
                    total_tokens=self._stats.total_tokens,
                    call_count=self._stats.call_count,
                    max_input_tokens=self._stats.max_input_tokens,
                    max_output_tokens=self._stats.max_output_tokens,
                    max_total_tokens=self._stats.max_total_tokens,
                    calls=self._stats.calls.copy(),
                )


def count_tokens_from_response(
    response: Any, model: Optional[str] = None, context: Optional[str] = None
) -> tuple[int, int]:
    """Extract and count tokens from an OpenAI-style response object"""
    try:
        if hasattr(response, "usage") and response.usage is not None:
            try:
                usage = response.usage
                input_tokens = getattr(usage, "prompt_tokens", 0)
                output_tokens = getattr(usage, "completion_tokens", 0)
            except AttributeError as e:
                print(f"Warning: Could not access usage attribute: {e}")
                input_tokens = output_tokens = 0

            counter = TokenCounter()
            counter._add_tokens(input_tokens, output_tokens, model, context)

            return input_tokens, output_tokens
        else:
            # If no usage info available, return 0,0 but don't add to counter
            return 0, 0
    except Exception:
        # If any error occurs, return 0,0 but don't add to counter
        return 0, 0


# Global convenience functions
def print_token_summary(
    app_tokens: Optional[Dict[str, int]] = None,
    save_file_prefix: Optional[str] = None,
    save_to_results: bool = True,
) -> None:
    """
    Print a comprehensive token usage summary with separate app and evaluation tokens.

    Args:
        app_tokens: Dict with keys 'input', 'output', 'total', 'calls' for app token usage.
                   If None, app tokens will be shown as 0 (useful for deep_eval case).
        save_file_prefix: Optional prefix for saved token file (e.g., 'generator', 'run_conversations').
                         If None, no file will be saved.
        save_to_results: Whether to save to results/token_usage directory (default True).
    """
    import datetime

    print("\n=== Token Usage Summary ===")

    # Get evaluation token stats
    counter = TokenCounter()
    eval_stats = counter._get_stats()

    # Handle app tokens (default to zero if None, for deep_eval case)
    if app_tokens is None:
        app_tokens = {"input": 0, "output": 0, "total": 0, "calls": 0}

    # Display app tokens
    print("\n📱 App Tokens (from chat agent):")
    print(f"  Input tokens: {app_tokens['input']:,}")
    print(f"  Output tokens: {app_tokens['output']:,}")
    print(f"  Total tokens: {app_tokens['total']:,}")
    print(f"  API calls: {app_tokens['calls']:,}")

    # Display evaluation tokens
    print("\n🔬 Evaluation Tokens (from evaluation LLM calls):")
    print(f"  Input tokens: {eval_stats.total_input_tokens:,}")
    print(f"  Output tokens: {eval_stats.total_output_tokens:,}")
    print(f"  Total tokens: {eval_stats.total_tokens:,}")
    print(f"  API calls: {eval_stats.call_count:,}")
    if eval_stats.call_count > 0:
        print(f"  Max single request input: {eval_stats.max_input_tokens:,}")
        print(f"  Max single request output: {eval_stats.max_output_tokens:,}")
        print(f"  Max single request total: {eval_stats.max_total_tokens:,}")

    # Calculate combined totals
    combined_input = app_tokens["input"] + eval_stats.total_input_tokens
    combined_output = app_tokens["output"] + eval_stats.total_output_tokens
    combined_total = app_tokens["total"] + eval_stats.total_tokens
    combined_calls = app_tokens["calls"] + eval_stats.call_count

    print("\n📊 Combined Totals:")
    print(f"  Input tokens: {combined_input:,}")
    print(f"  Output tokens: {combined_output:,}")
    print(f"  Total tokens: {combined_total:,}")
    print(f"  API calls: {combined_calls:,}")
    if eval_stats.call_count > 0:
        print(f"  Max single request input: {eval_stats.max_input_tokens:,}")
        print(f"  Max single request output: {eval_stats.max_output_tokens:,}")
        print(f"  Max single request total: {eval_stats.max_total_tokens:,}")

    # Save token stats to file if requested
    if save_file_prefix and (eval_stats.call_count > 0 or app_tokens["calls"] > 0):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        if save_to_results:
            token_dir = "results/token_usage"
            token_file = os.path.join(token_dir, f"{save_file_prefix}_{timestamp}.json")
        else:
            token_file = f"{save_file_prefix}_{timestamp}.json"

        # Create comprehensive token data including app and evaluation tokens
        comprehensive_stats = {
            "summary": {
                "total_input_tokens": combined_input,
                "total_output_tokens": combined_output,
                "total_tokens": combined_total,
                "call_count": combined_calls,
                "max_input_tokens": eval_stats.max_input_tokens,
                "max_output_tokens": eval_stats.max_output_tokens,
                "max_total_tokens": eval_stats.max_total_tokens,
            },
            "app_tokens": app_tokens,
            "evaluation_tokens": {
                "total_input_tokens": eval_stats.total_input_tokens,
                "total_output_tokens": eval_stats.total_output_tokens,
                "total_tokens": eval_stats.total_tokens,
                "call_count": eval_stats.call_count,
                "max_input_tokens": eval_stats.max_input_tokens,
                "max_output_tokens": eval_stats.max_output_tokens,
                "max_total_tokens": eval_stats.max_total_tokens,
            },
            "detailed_calls": [
                {
                    "input_tokens": call.input_tokens,
                    "output_tokens": call.output_tokens,
                    "total_tokens": call.total_tokens,
                    "model": call.model,
                    "context": call.context,
                    "timestamp": call.timestamp,
                }
                for call in getattr(eval_stats, "calls", [])
            ],
        }

        if save_to_results:
            os.makedirs(token_dir, exist_ok=True)

        with open(token_file, "w") as f:
            json.dump(comprehensive_stats, f, indent=2)
        print(f"Token usage saved to: {token_file}")
