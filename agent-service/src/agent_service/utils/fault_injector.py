"""
Fault injection wrapper for testing API resilience.

This wrapper injects failures ONLY into responses.create() calls (the main
response generation endpoint). All other API calls (models.list(),
moderations.create(), vector_stores.list(), etc.) pass through unchanged
to avoid breaking initialization, safety checks, and infrastructure operations.

Enabled via environment variables:
  FAULT_INJECTION_ENABLED=1                # Enable fault injection
  FAULT_INJECTION_RATE=0.1                 # 10% failure rate (default: 0.1)
  FAULT_INJECTION_ERROR_TYPE=timeout       # timeout|connection|api_error|empty_response|rand
                                           # - timeout: Raise TimeoutError
                                           # - connection: Raise ConnectionError
                                           # - api_error: Raise RuntimeError
                                           # - empty_response: Return empty response (triggers retry logic)
                                           # - rand: Randomly choose one of the above
"""

import os
import random
from typing import Any


class EmptyResponse:
    """Mock response object that simulates an empty response from the API.

    This triggers the retry logic in create_response_with_retry() which
    checks for empty responses.
    """

    def __init__(self):
        self.output_text = ""  # Empty text
        self.output = []  # Empty output array
        self.status = "completed"  # Status looks OK
        self.error = None  # No explicit error
        self.id = "fault-injection-empty"  # Valid ID to avoid quota check failures


class FaultInjectingAsyncLlamaStackClient:
    """Wrapper that randomly injects failures into AsyncLlamaStackClient calls."""

    # All possible error types for random selection
    ERROR_TYPES = ["timeout", "connection", "api_error", "empty_response"]

    def __init__(
        self,
        wrapped_client: Any,
        failure_rate: float = 0.1,
        error_type: str = "timeout",
    ):
        """
        Args:
            wrapped_client: The real AsyncLlamaStackClient to wrap
            failure_rate: Probability of failure (0.0 to 1.0). E.g., 0.1 = 10% chance
            error_type: Type of error to simulate (timeout|connection|api_error|empty_response|rand)
        """
        self._wrapped = wrapped_client
        self._failure_rate = max(0.0, min(1.0, failure_rate))
        self._error_type = error_type

        # Assign unique instance ID for tracking
        self._instance_id = id(self)

        # Use independent Random instance seeded with OS-level random bytes
        import os

        self._random = random.Random(os.urandom(32))

        # Expose wrapped client's attributes
        # Only inject faults into responses.create() - all other APIs pass through unchanged
        self.responses = self._wrap_namespace(
            wrapped_client.responses, inject_faults=True
        )
        self.moderations = self._wrap_namespace(
            wrapped_client.moderations, inject_faults=False
        )
        self.models = self._wrap_namespace(wrapped_client.models, inject_faults=False)
        self.vector_stores = self._wrap_namespace(
            wrapped_client.vector_stores, inject_faults=False
        )

    def _should_fail(self) -> bool:
        """Randomly determine if this request should fail."""
        rand_value = self._random.random()
        will_fail = rand_value < self._failure_rate

        # Log each decision for debugging clustering issues
        from shared_models import configure_logging

        logger = configure_logging("agent-service")
        logger.info(
            "Fault injection decision",
            instance_id=self._instance_id,
            random_value=f"{rand_value:.4f}",
            failure_threshold=self._failure_rate,
            will_fail=will_fail,
        )

        return will_fail

    def _pick_error_type(self) -> str:
        """Pick an error type (handles 'rand' option)."""
        if self._error_type == "rand":
            return self._random.choice(self.ERROR_TYPES)
        return self._error_type

    def _simulate_failure(self, error_type: str) -> Any:
        """Simulate a failure by either raising an error or returning empty response.

        Args:
            error_type: The type of error to simulate (already resolved from rand if needed)

        Returns:
            EmptyResponse object if error_type is 'empty_response', otherwise raises an exception.
        """
        if error_type == "timeout":
            raise TimeoutError("Simulated timeout error (fault injection)")
        elif error_type == "connection":
            raise ConnectionError("Simulated connection error (fault injection)")
        elif error_type == "api_error":
            raise RuntimeError("Simulated API error (fault injection)")
        elif error_type == "empty_response":
            # Return empty response to trigger retry logic
            return EmptyResponse()
        else:
            raise Exception(f"Simulated error: {error_type} (fault injection)")

    def _wrap_namespace(self, namespace: Any, inject_faults: bool = False) -> Any:
        """Wrap a namespace (like responses, models) to inject faults.

        Args:
            namespace: The namespace to wrap (e.g., responses, models)
            inject_faults: If True, inject faults into create() calls. If False, pass through.
        """

        class NamespaceWrapper:
            def __init__(wrapper_self, ns, should_inject):  # type: ignore[no-untyped-def]
                wrapper_self._ns = ns
                wrapper_self._should_inject = should_inject

            async def create(wrapper_self, *args, **kwargs):  # type: ignore[no-untyped-def]
                # Only inject fault if this namespace is configured for fault injection
                if wrapper_self._should_inject and self._should_fail():
                    from shared_models import configure_logging

                    logger = configure_logging("agent-service")

                    # Determine actual error type (handles 'rand')
                    actual_error_type = self._pick_error_type()

                    logger.warning(
                        "FAULT INJECTION: Simulating API failure in responses.create()",
                        failure_rate=self._failure_rate,
                        configured_error_type=self._error_type,
                        actual_error_type=actual_error_type,
                    )

                    # Simulate failure - may raise exception or return EmptyResponse
                    return self._simulate_failure(actual_error_type)

                # Call real method
                return await wrapper_self._ns.create(*args, **kwargs)

            async def list(wrapper_self, *args, **kwargs):  # type: ignore[no-untyped-def]
                # Never inject faults in list() calls - they're used for initialization
                return await wrapper_self._ns.list(*args, **kwargs)

        return NamespaceWrapper(namespace, inject_faults)


def should_enable_fault_injection() -> bool:
    """Check if fault injection should be enabled."""
    return os.environ.get("FAULT_INJECTION_ENABLED", "0") == "1"


def get_fault_injection_rate() -> float:
    """Get configured failure rate (0.0 to 1.0)."""
    try:
        rate = float(os.environ.get("FAULT_INJECTION_RATE", "0.1"))
        return max(0.0, min(1.0, rate))
    except ValueError:
        return 0.1


def get_fault_injection_error_type() -> str:
    """Get configured error type."""
    return os.environ.get("FAULT_INJECTION_ERROR_TYPE", "timeout")


def wrap_client_with_fault_injection(client: Any) -> Any:
    """
    Conditionally wrap client with fault injection based on environment config.

    Returns:
        Either the wrapped client (if enabled) or the original client
    """
    if should_enable_fault_injection():
        rate = get_fault_injection_rate()
        error_type = get_fault_injection_error_type()

        from shared_models import configure_logging

        logger = configure_logging("agent-service")

        # Build error type description
        if error_type == "rand":
            error_type_desc = f"rand (randomly: {', '.join(FaultInjectingAsyncLlamaStackClient.ERROR_TYPES)})"
        else:
            error_type_desc = error_type

        logger.warning(
            "FAULT INJECTION ENABLED - responses.create() calls will randomly fail",
            failure_rate=f"{rate * 100}%",
            error_type=error_type_desc,
            scope="responses.create() only - other API calls unaffected",
        )

        return FaultInjectingAsyncLlamaStackClient(client, rate, error_type)

    return client
