"""Factory for creating LlamaStack clients (both native and OpenAI-compatible).

This module provides centralized factory functions for creating LlamaStack clients:

1. Native LlamaStack client (LlamaStackClient):
   - Model listing (models.list())
   - Response generation (responses.create())
   - Content moderation (moderations.create())

2. OpenAI-compatible client (openai.OpenAI):
   - Vector store management (knowledge bases)
   - Assistant/thread operations
   - File uploads

Note: LlamaStack running in-cluster doesn't require authentication by default,
so the api_key is set to a dummy value to satisfy the OpenAI client library's
requirement that an API key be provided. The actual security boundary is at
the network level (services communicate within the Kubernetes cluster).
"""

import os
from typing import Any, Optional

import openai
from shared_models import configure_logging

logger = configure_logging("agent-service")


def create_llamastack_openai_client(
    timeout: Optional[float] = None,
    llamastack_host: Optional[str] = None,
    port: Optional[int] = None,
    api_key: Optional[str] = None,
    openai_base_path: Optional[str] = None,
) -> openai.OpenAI:
    """
    Create an OpenAI client configured for LlamaStack.

    This function provides a centralized way to create OpenAI clients with
    consistent configuration across the agent service. All configuration can
    be overridden via parameters or environment variables.

    Args:
        timeout: Request timeout in seconds.
            Default: LLAMASTACK_TIMEOUT env var or 120
        llamastack_host: LlamaStack hostname (without protocol).
            Default: LLAMASTACK_SERVICE_HOST env var (Kubernetes auto-injected) or "llamastack"
        port: LlamaStack port number.
            Default: LLAMASTACK_CLIENT_PORT env var (Helm override) or
                     LLAMASTACK_SERVICE_PORT env var (Kubernetes auto-injected) or 8321
        api_key: API key for authentication.
            Default: LLAMASTACK_API_KEY env var or "dummy-key"
        openai_base_path: OpenAI API base path.
            Default: LLAMASTACK_OPENAI_BASE_PATH env var or "/v1/openai/v1"

    Returns:
        Configured OpenAI client instance

    Environment Variables (priority order):
        LLAMASTACK_SERVICE_HOST: Kubernetes-injected hostname (auto-discovered from service)
        LLAMASTACK_CLIENT_PORT: Helm-configurable port override (takes precedence)
        LLAMASTACK_SERVICE_PORT: Kubernetes-injected port (auto-discovered from service)
        LLAMASTACK_API_KEY: API key (default: "dummy-key")
        LLAMASTACK_OPENAI_BASE_PATH: OpenAI API path (default: "/v1/openai/v1")
        LLAMASTACK_TIMEOUT: Request timeout in seconds (default: "120")

    """
    # Get configuration from parameters or environment variables
    # Host: Use Kubernetes auto-injected LLAMASTACK_SERVICE_HOST
    host = llamastack_host or os.environ.get("LLAMASTACK_SERVICE_HOST", "llamastack")

    # Port: Check Helm override first, then Kubernetes auto-injected, then default
    # Note: We avoid LLAMASTACK_PORT as Kubernetes sets it to "tcp://host:port" format
    port_str = os.environ.get("LLAMASTACK_CLIENT_PORT") or os.environ.get(
        "LLAMASTACK_SERVICE_PORT", "8321"
    )
    port_num = port or int(port_str)
    key = api_key or os.environ.get("LLAMASTACK_API_KEY", "dummy-key")
    path = openai_base_path or os.environ.get(
        "LLAMASTACK_OPENAI_BASE_PATH", "/v1/openai/v1"
    )
    timeout_val = timeout or float(os.environ.get("LLAMASTACK_TIMEOUT", "120"))

    # Strip protocol if present in hostname
    if host.startswith(("http://", "https://")):
        host = host.split("://", 1)[1]

    # Construct base URL
    base_url = f"http://{host}:{port_num}{path}"

    logger.debug(
        "Creating OpenAI client for LlamaStack",
        base_url=base_url,
        timeout=timeout_val,
    )

    return openai.OpenAI(
        api_key=key,
        base_url=base_url,
        timeout=timeout_val,
    )


def create_llamastack_client(
    timeout: Optional[float] = None,
    llamastack_host: Optional[str] = None,
    port: Optional[int] = None,
) -> Any:
    """
    Create a native LlamaStack client.

    This client is used for:
    - Model listing (models.list())
    - Response generation (responses.create())
    - Content moderation (moderations.create())

    Args:
        timeout: Request timeout in seconds.
            Default: LLAMASTACK_TIMEOUT env var or 120.0
        llamastack_host: LlamaStack hostname (without protocol).
            Default: LLAMASTACK_SERVICE_HOST env var (Kubernetes auto-injected) or "llamastack"
        port: LlamaStack port number.
            Default: LLAMASTACK_CLIENT_PORT env var (Helm override) or
                     LLAMASTACK_SERVICE_PORT env var (Kubernetes auto-injected) or 8321

    Returns:
        Configured LlamaStackClient instance

    Environment Variables (priority order):
        LLAMASTACK_SERVICE_HOST: Kubernetes-injected hostname (auto-discovered from service)
        LLAMASTACK_CLIENT_PORT: Helm-configurable port override (takes precedence)
        LLAMASTACK_SERVICE_PORT: Kubernetes-injected port (auto-discovered from service)
        LLAMASTACK_TIMEOUT: Request timeout in seconds (default: "120.0")

    """
    from llama_stack_client import LlamaStackClient

    # Get configuration from parameters or environment variables
    # Host: Use Kubernetes auto-injected LLAMASTACK_SERVICE_HOST
    host = llamastack_host or os.environ.get("LLAMASTACK_SERVICE_HOST", "llamastack")

    # Port: Check Helm override first, then Kubernetes auto-injected, then default
    # Note: We avoid LLAMASTACK_PORT as Kubernetes sets it to "tcp://host:port" format
    port_str = os.environ.get("LLAMASTACK_CLIENT_PORT") or os.environ.get(
        "LLAMASTACK_SERVICE_PORT", "8321"
    )
    port_num = port or int(port_str)
    timeout_val = timeout or float(os.environ.get("LLAMASTACK_TIMEOUT", "120.0"))

    # Strip protocol if present in hostname
    if host.startswith(("http://", "https://")):
        host = host.split("://", 1)[1]

    # Construct base URL
    base_url = f"http://{host}:{port_num}"

    logger.debug(
        "Creating LlamaStack client",
        base_url=base_url,
        timeout=timeout_val,
    )

    return LlamaStackClient(
        base_url=base_url,
        timeout=timeout_val,
    )


def create_async_llamastack_client(
    timeout: Optional[float] = None,
    llamastack_host: Optional[str] = None,
    port: Optional[int] = None,
) -> Any:
    """
    Create an async native LlamaStack client.

    This async client is used for:
    - Model listing (await models.list())
    - Response generation (await responses.create())
    - Content moderation (await moderations.create())

    Uses httpx.AsyncClient under the hood for true async I/O, allowing
    high concurrency without blocking the event loop or requiring thread pools.

    Args:
        timeout: Request timeout in seconds.
            Default: LLAMASTACK_TIMEOUT env var or 120.0
        llamastack_host: LlamaStack hostname (without protocol).
            Default: LLAMASTACK_SERVICE_HOST env var (Kubernetes auto-injected) or "llamastack"
        port: LlamaStack port number.
            Default: LLAMASTACK_CLIENT_PORT env var (Helm override) or
                     LLAMASTACK_SERVICE_PORT env var (Kubernetes auto-injected) or 8321

    Returns:
        Configured AsyncLlamaStackClient instance

    Environment Variables (priority order):
        LLAMASTACK_SERVICE_HOST: Kubernetes-injected hostname (auto-discovered from service)
        LLAMASTACK_CLIENT_PORT: Helm-configurable port override (takes precedence)
        LLAMASTACK_SERVICE_PORT: Kubernetes-injected port (auto-discovered from service)
        LLAMASTACK_TIMEOUT: Request timeout in seconds (default: "120.0")

    """
    from llama_stack_client import AsyncLlamaStackClient

    # Get configuration from parameters or environment variables
    # Host: Use Kubernetes auto-injected LLAMASTACK_SERVICE_HOST
    host = llamastack_host or os.environ.get("LLAMASTACK_SERVICE_HOST", "llamastack")

    # Port: Check Helm override first, then Kubernetes auto-injected, then default
    # Note: We avoid LLAMASTACK_PORT as Kubernetes sets it to "tcp://host:port" format
    port_str = os.environ.get("LLAMASTACK_CLIENT_PORT") or os.environ.get(
        "LLAMASTACK_SERVICE_PORT", "8321"
    )
    port_num = port or int(port_str)
    timeout_val = timeout or float(os.environ.get("LLAMASTACK_TIMEOUT", "120.0"))

    # Strip protocol if present in hostname
    if host.startswith(("http://", "https://")):
        host = host.split("://", 1)[1]

    # Construct base URL
    base_url = f"http://{host}:{port_num}"

    logger.debug(
        "Creating async LlamaStack client",
        base_url=base_url,
        timeout=timeout_val,
    )

    client = AsyncLlamaStackClient(
        base_url=base_url,
        timeout=timeout_val,
    )

    # Wrap with fault injection if enabled
    from .fault_injector import wrap_client_with_fault_injection

    return wrap_client_with_fault_injection(client)
