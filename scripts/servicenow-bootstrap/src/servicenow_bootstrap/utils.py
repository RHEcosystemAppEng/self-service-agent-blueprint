"""Utility functions for ServiceNow automation scripts."""

import os
import sys


def get_env_var(var_name: str, required: bool = True) -> str:
    """Get environment variable with optional requirement check.

    Args:
        var_name: The name of the environment variable to retrieve
        required: Whether the variable is required (default: True)

    Returns:
        The environment variable value or empty string if not required and not set

    Raises:
        SystemExit: If a required variable is not set
    """
    value = os.getenv(var_name)
    if required and not value:
        print(f"❌ Required environment variable not set: {var_name}")
        sys.exit(1)
    return value or ""
