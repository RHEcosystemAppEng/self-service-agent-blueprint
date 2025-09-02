"""Base integration handler interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig


class IntegrationResult:
    """Result of an integration delivery attempt."""

    def __init__(
        self,
        success: bool,
        status: DeliveryStatus,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
    ):
        self.success = success
        self.status = status
        self.message = message
        self.metadata = metadata or {}
        self.retry_after = retry_after  # Seconds to wait before retry


class BaseIntegrationHandler(ABC):
    """Base class for integration handlers."""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """
        Deliver a message via this integration.

        Args:
            request: The delivery request with content and metadata
            config: User's integration configuration
            template_content: Rendered template content (subject, body)

        Returns:
            IntegrationResult with delivery status and metadata
        """
        pass

    @abstractmethod
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate integration configuration.

        Args:
            config: Integration configuration to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the integration is healthy and available.

        Returns:
            True if healthy, False otherwise
        """
        return True

    def get_required_config_fields(self) -> list[str]:
        """
        Get list of required configuration fields.

        Returns:
            List of required field names
        """
        return []

    def get_optional_config_fields(self) -> list[str]:
        """
        Get list of optional configuration fields.

        Returns:
            List of optional field names
        """
        return []
