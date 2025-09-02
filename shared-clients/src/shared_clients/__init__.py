"""
Shared client libraries for the self-service agent blueprint.

This package provides reusable client classes for interacting with various
components of the self-service agent system, including the Request Manager,
Agent Service, and other services.
"""

from .request_manager_client import CLIChatClient, RequestManagerClient

__all__ = [
    "RequestManagerClient",
    "CLIChatClient",
]
