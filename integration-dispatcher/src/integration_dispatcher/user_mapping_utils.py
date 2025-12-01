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

    # Convenience function for Slack
    await store_slack_user_mapping("user@example.com", "U1234567890", "slack_service")
"""

from datetime import datetime, timezone
from typing import Any, Optional

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


async def store_email_user_mapping(
    user_email: str, created_by: str = "email_service"
) -> None:
    """Store an email user mapping (convenience function).

    For email, the integration_user_id is the email_address itself.
    """
    await store_user_mapping(
        user_email=user_email,
        integration_user_id=user_email,
        integration_type=IntegrationType.EMAIL,
        created_by=created_by,
    )


async def resolve_user_id_from_email(
    email_address: str,
    integration_type: IntegrationType,
    db: Any,
    default_user_id: str,
    integration_specific_id: Optional[str] = None,
    created_by: str = "system",
) -> str:
    """Resolve user_id from email address, checking for existing mappings and maintaining user identity.

    This function:
    1. Checks for integration-specific mapping first
    2. If not found, checks if email exists in any other integration mapping
    3. If found, reuses existing user_id and creates mapping with integration_specific_id (or existing user_id)
    4. If not found, creates new mapping with default_user_id and integration_specific_id

    Args:
        email_address: The user's email address
        integration_type: The integration type to create mapping for (e.g., EMAIL, SLACK)
        db: Database session to use for queries
        default_user_id: The user_id to use if no existing mapping is found
        integration_specific_id: The integration-specific ID to store in integration_user_id
            (e.g., Slack user ID). If None, uses the resolved user_id.
        created_by: Identifier for who is creating this mapping

    Returns:
        str: The resolved user_id (either existing or default)
    """
    from sqlalchemy import select

    # Check for integration-specific mapping first
    stmt = select(UserIntegrationMapping).where(
        UserIntegrationMapping.user_email == email_address,
        UserIntegrationMapping.integration_type == integration_type,
    )
    result = await db.execute(stmt)
    integration_mapping = result.scalar_one_or_none()

    if integration_mapping:
        logger.debug(
            "Found existing mapping for integration",
            email_address=email_address,
            integration_type=integration_type.value,
            integration_user_id=integration_mapping.integration_user_id,
        )
        # For system user_id, we need to use the email_address (user_email field)
        # The integration_user_id is integration-specific (e.g., Slack user ID) and used for lookups
        # But the system user_id should be consistent - for both Slack and Email, we use the email
        # However, for backwards compatibility, some integrations might use integration_user_id as user_id
        # So we return the email_address which is the consistent system user_id
        return email_address

    # Check if email exists in any other integration mapping
    # This handles the case where a user already has a mapping via another integration
    # Use scalars().first() instead of scalar_one_or_none() since there can be multiple mappings
    # (e.g., both SLACK and EMAIL for the same email)
    stmt = select(UserIntegrationMapping).where(
        UserIntegrationMapping.user_email == email_address
    )
    result = await db.execute(stmt)
    existing_mapping = result.scalars().first()

    if existing_mapping:
        # User already exists via another integration - use email_address as the consistent user_id
        # The system expects email_address as the user_id for both Slack and Email
        # Use integration_specific_id if provided, otherwise use email_address
        # For Slack: integration_specific_id should be slack_user_id
        # For Email: integration_specific_id should be email_address
        integration_id = (
            integration_specific_id
            if integration_specific_id is not None
            else email_address
        )
        logger.info(
            "Found existing mapping for email from another integration, creating mapping with same user_id",
            email_address=email_address,
            integration_type=integration_type.value,
            existing_integration_type=existing_mapping.integration_type.value,
            existing_integration_user_id=existing_mapping.integration_user_id,
            integration_specific_id=integration_id,
        )
        # Create mapping using integration_specific_id for integration_user_id
        # but the system will use email_address as the user_id for requests (consistent across integrations)
        await store_user_mapping(
            user_email=email_address,
            integration_user_id=integration_id,
            integration_type=integration_type,
            created_by=created_by,
        )
        # Always return email_address as the system user_id for consistency
        return email_address

    # No mapping found - create one for new user
    # Use integration_specific_id if provided, otherwise use default_user_id
    integration_id = (
        integration_specific_id
        if integration_specific_id is not None
        else default_user_id
    )
    logger.info(
        "No mapping found for email, creating mapping for new user",
        email_address=email_address,
        integration_type=integration_type.value,
        default_user_id=default_user_id,
        integration_specific_id=integration_id,
    )
    await store_user_mapping(
        user_email=email_address,
        integration_user_id=integration_id,
        integration_type=integration_type,
        created_by=created_by,
    )
    return default_user_id
