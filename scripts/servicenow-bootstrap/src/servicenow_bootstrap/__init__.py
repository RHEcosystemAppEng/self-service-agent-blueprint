"""ServiceNow PDI Setup Automation Package.

This package provides automation scripts to help set up a ServiceNow Personal
Development Instance (PDI) for testing the Blueprint's integration with ServiceNow.
"""

__version__ = "0.1.0"

from .create_mcp_agent_api_key import ServiceNowAPIAutomation
from .create_mcp_agent_user import ServiceNowUserAutomation
from .create_pc_refresh_service_catalog_item import ServiceNowCatalogAutomation
from .utils import get_env_var

__all__ = [
    "ServiceNowAPIAutomation",
    "ServiceNowCatalogAutomation",
    "ServiceNowUserAutomation",
    "get_env_var",
]
