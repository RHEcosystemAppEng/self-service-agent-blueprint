"""Test integration handler for E2E testing."""

import os
from typing import Any, Dict

import structlog
from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig

from .base import BaseIntegrationHandler, IntegrationResult

logger = structlog.get_logger()


class TestIntegrationHandler(BaseIntegrationHandler):
    """Handler for test message delivery - logs to console."""

    def __init__(self):
        super().__init__()
        self.enabled = os.getenv("TEST_INTEGRATION_ENABLED", "true").lower() == "true"

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """Deliver test message by logging to console."""
        try:
            test_config = config.config

            # Create test message payload
            test_message = {
                "request_id": request.request_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "subject": template_content.get("subject", "Agent Response"),
                "content": template_content.get("body", ""),
                "template_variables": request.template_variables,
                "test_config": test_config,
                "delivery_method": "TEST_INTEGRATION",
            }

            # Log the message (this will appear in Integration Dispatcher logs)
            logger.info("Test integration delivery", test_message=test_message)

            return IntegrationResult(
                success=True,
                status=DeliveryStatus.DELIVERED,
                message="Test message delivered successfully",
                metadata={
                    "delivery_method": "test_integration",
                    "message_length": len(template_content.get("body", "")),
                    "test_id": test_config.get("test_id"),
                },
            )

        except Exception as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Test integration error: {str(e)}",
            )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate test configuration."""
        # Test integration accepts any configuration
        return True

    async def health_check(self) -> bool:
        """Test integration health check - configurable via environment."""
        import structlog

        logger = structlog.get_logger()
        # Only log if enabled to reduce noise
        if self.enabled:
            logger.info(
                "TEST integration health check",
                enabled=self.enabled,
            )
        return self.enabled

    def get_required_config_fields(self) -> list[str]:
        """No required fields for test integration."""
        return []

    def get_optional_config_fields(self) -> list[str]:
        """Optional test configuration fields."""
        return [
            "test_id",
            "test_name",
            "output_format",
            "include_metadata",
        ]
