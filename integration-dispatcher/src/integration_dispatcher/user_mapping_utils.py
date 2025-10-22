"""
Shared utilities for user mapping operations.

This module provides generic functions for storing user mappings across different
integration types (Slack, Teams, Discord, Web, etc.). It supports both generic
functions and convenience functions for specific integration types.

Usage:
    # Generic function (supports any integration type)
    await store_user_mapping(
        user_email="user@example.com",
        integration_user_id="U1234567890",
        integration_type=IntegrationType.SLACK,
        created_by="my_service"
    )

    # Convenience functions (easier to use for specific types)
    await store_slack_user_mapping("user@example.com", "U1234567890", "slack_service")
    await store_email_user_mapping("user@example.com", "E1234567890", "email_service")
    await store_webhook_user_mapping("user@example.com", "W1234567890", "webhook_service")
    await store_test_user_mapping("user@example.com", "T1234567890", "test_service")
"""

from datetime import datetime, timezone

from shared_models import configure_logging
from shared_models.database import get_database_manager
from shared_models.models import IntegrationType, UserIntegrationMapping
from sqlalchemy.dialects.postgresql import insert

logger = configure_logging("integration-dispatcher")


async def store_user_mapping(
    user_email: str,
    integration_user_id: str,
    integration_type: IntegrationType,
    created_by: str = "system",
) -> None:
    """
    Store the email -> integration user ID mapping for future use.

    Args:
        user_email: The user's email address
        integration_user_id: The integration-specific user ID (e.g., Slack user ID, Teams user ID)
        integration_type: The type of integration (SLACK, TEAMS, etc.)
        created_by: Identifier for who created this mapping
    """
    try:
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            # Use upsert pattern - update if exists, insert if not
            stmt = insert(UserIntegrationMapping).values(
                user_email=user_email,
                integration_type=integration_type,
                integration_user_id=integration_user_id,
                last_validated_at=datetime.now(timezone.utc),
                validation_attempts=0,  # Reset attempts for new/updated mapping
                last_validation_error=None,  # Clear any previous errors
                created_by=created_by,
            )

            # On conflict, update the integration user ID and validation timestamp
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_email", "integration_type"],
                set_={
                    "integration_user_id": stmt.excluded.integration_user_id,
                    "last_validated_at": stmt.excluded.last_validated_at,
                    "validation_attempts": 0,  # Reset attempts
                    "last_validation_error": None,  # Clear errors
                    "updated_at": datetime.now(timezone.utc),
                },
            )

            await db.execute(stmt)
            await db.commit()

            logger.info(
                "Stored user mapping",
                user_email=user_email,
                integration_user_id=integration_user_id,
                integration_type=integration_type.value,
                created_by=created_by,
            )

    except Exception as e:
        logger.error(
            "Error storing user mapping",
            user_email=user_email,
            integration_user_id=integration_user_id,
            integration_type=integration_type.value,
            created_by=created_by,
            error=str(e),
        )


# Convenience functions for specific integration types
async def store_slack_user_mapping(
    user_email: str, slack_user_id: str, created_by: str = "system"
) -> None:
    """Store a Slack user mapping (convenience function)."""
    await store_user_mapping(
        user_email=user_email,
        integration_user_id=slack_user_id,
        integration_type=IntegrationType.SLACK,
        created_by=created_by,
    )
