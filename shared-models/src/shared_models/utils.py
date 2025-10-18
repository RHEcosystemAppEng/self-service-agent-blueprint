"""Shared utilities for database and enum handling."""

from enum import Enum
from typing import Any, Union


def get_enum_value(enum_obj: Union[Enum, str, Any]) -> str:
    """
    Safely extract the value from an enum object or convert to string.

    This function provides defensive handling for cases where an object
    might be an enum with a .value attribute, or just a string/other type.

    For database storage, SQLAlchemy SQLEnum columns expect the actual enum
    string values (e.g., "WEB", "SLACK") as defined in the enum classes.
    This function ensures we always return the proper string representation.

    Args:
        enum_obj: An enum instance, string, or other object

    Returns:
        str: The enum's .value if it exists, otherwise str(enum_obj)

    Examples:
        >>> from shared_models.models import IntegrationType
        >>> get_enum_value(IntegrationType.WEB)
        'WEB'
        >>> get_enum_value("WEB")
        'WEB'
        >>> get_enum_value("web")  # Note: Should be handled by field validators
        'web'

    Note:
        For database operations, input strings should be converted to proper
        enum instances via Pydantic field validators before reaching this function.
    """
    if hasattr(enum_obj, "value"):
        return str(enum_obj.value)
    return str(enum_obj)


def generate_fallback_user_id(request_id: str | None) -> str:
    """
    Generate a fallback user_id when the original user_id is missing.

    This function creates a unique fallback user_id using the request_id
    prefix to ensure uniqueness and traceability.

    Args:
        request_id: The request ID to use for generating the fallback (can be None)

    Returns:
        str: A fallback user_id in the format "unknown-{request_id_prefix}" or "unknown-{unique_id}" if request_id is None

    Examples:
        >>> generate_fallback_user_id("abc12345-def6-7890-ghij-klmnopqrstuv")
        'unknown-abc12345'
        >>> generate_fallback_user_id("short")
        'unknown-short'
        >>> generate_fallback_user_id(None)
        'unknown-a1b2c3d4'  # unique identifier
    """
    if request_id is None:
        import uuid

        return f"unknown-{str(uuid.uuid4())[:8]}"
    return f"unknown-{request_id[:8]}"
