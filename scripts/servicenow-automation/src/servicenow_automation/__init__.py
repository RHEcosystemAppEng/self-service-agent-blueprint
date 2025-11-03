"""ServiceNow PDI Setup Automation Package.

This package provides automation scripts to help set up a ServiceNow Personal
Development Instance (PDI) for testing the Blueprint's integration with ServiceNow.
"""

__version__ = "0.1.0"

from .api_automation import ServiceNowAPIAutomation
from .catalog_automation import ServiceNowCatalogAutomation
from .user_automation import ServiceNowUserAutomation

__all__ = [
    "ServiceNowAPIAutomation",
    "ServiceNowCatalogAutomation",
    "ServiceNowUserAutomation",
]
