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

from shared_models import configure_logging, get_or_create_canonical_user
from shared_models.database import get_database_manager
from shared_models.models import IntegrationType, UserIntegrationMapping
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = configure_logging("integration-dispatcher")


async def store_user_mapping(
    user_email: str,
    integration_user_id: str,
    integration_type: IntegrationType,
    created_by: str = "system",
    canonical_user_id: Optional[str] = None,
) -> str:
    """
    Store the integration user ID mapping, creating/getting canonical user if needed.

    Args:
        user_email: The user's email address
        integration_user_id: The integration-specific user ID (e.g., Slack user ID, Teams user ID)
        integration_type: The type of integration (SLACK, TEAMS, etc.)
        created_by: Identifier for who created this mapping
        canonical_user_id: Optional canonical user_id. If None, will be resolved from email.

    Returns:
        str: The canonical user_id
    """
    try:
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            # Get or create canonical user
            if canonical_user_id is None:
                canonical_user_id = await get_or_create_canonical_user(user_email, db)

            # Use upsert pattern - update if exists, insert if not
            stmt = insert(UserIntegrationMapping).values(
                user_id=canonical_user_id,
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
                index_elements=["user_id", "integration_type"],
                set_={
                    "integration_user_id": stmt.excluded.integration_user_id,
                    "user_email": stmt.excluded.user_email,  # Update email if changed
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
                canonical_user_id=canonical_user_id,
                user_email=user_email,
                integration_user_id=integration_user_id,
                integration_type=integration_type.value,
                created_by=created_by,
            )

            return canonical_user_id

    except Exception as e:
        logger.error(
            "Error storing user mapping",
            user_email=user_email,
            integration_user_id=integration_user_id,
            integration_type=integration_type.value,
            created_by=created_by,
            error=str(e),
        )
        raise


# Convenience functions for specific integration types
async def store_slack_user_mapping(
    user_email: str, slack_user_id: str, created_by: str = "system"
) -> str:
    """Store a Slack user mapping (convenience function).

    Returns:
        str: The canonical user_id
    """
    return await store_user_mapping(
        user_email=user_email,
        integration_user_id=slack_user_id,
        integration_type=IntegrationType.SLACK,
        created_by=created_by,
    )


async def ensure_email_mapping_consistency(
    email_address: str,
    resolved_user_id: str,
    integration_type: IntegrationType,
    integration_user_id: str,
    db: AsyncSession,
    context: Optional[str] = None,
) -> str:
    """Ensure the resolved user_id matches any existing EMAIL mapping.

    If an EMAIL mapping exists with a different canonical user_id, this function
    updates the integration mapping to use the EMAIL mapping's canonical user_id
    to maintain consistency.

    Args:
        email_address: The user's email address
        resolved_user_id: The canonical user_id resolved from the integration
        integration_type: The integration type (e.g., SLACK)
        integration_user_id: The integration-specific user ID (e.g., Slack user ID)
        db: Database session
        context: Optional context string for logging

    Returns:
        str: The canonical user_id (may be updated to match EMAIL mapping)
    """
    # Check if EMAIL mapping exists
    stmt = select(UserIntegrationMapping).where(
        UserIntegrationMapping.user_email == email_address,
        UserIntegrationMapping.integration_type == IntegrationType.EMAIL,
    )
    result = await db.execute(stmt)
    email_mapping = result.scalar_one_or_none()

    if email_mapping:
        email_canonical_user_id = str(email_mapping.user_id)
        if resolved_user_id != email_canonical_user_id:
            logger.warning(
                "Resolved user_id doesn't match EMAIL mapping, fixing",
                context=context,
                email_address=email_address,
                resolved_canonical_user_id=resolved_user_id,
                email_canonical_user_id=email_canonical_user_id,
            )
            # Use the EMAIL mapping's canonical user_id instead
            resolved_user_id = email_canonical_user_id
            # Update the integration mapping to use the correct canonical user_id
            await store_user_mapping(
                user_email=email_address,
                integration_user_id=integration_user_id,
                integration_type=integration_type,
                created_by="email_mapping_consistency_fix",
                canonical_user_id=email_canonical_user_id,
            )

    return resolved_user_id


async def resolve_user_id_from_integration_id(
    integration_user_id: str,
    integration_type: IntegrationType,
    db: Any,
    created_by: str = "system",
) -> Optional[str]:
    """Resolve canonical user_id from integration-specific user ID (e.g., Slack user ID).

    This is used when email is not available (e.g., Slack API fails to return email).

    Args:
        integration_user_id: The integration-specific user ID (e.g., Slack user ID)
        integration_type: The integration type (e.g., SLACK)
        db: Database session
        created_by: Identifier for who is creating this lookup

    Returns:
        Optional[str]: The canonical user_id (UUID as string) if found, None otherwise
    """
    from sqlalchemy import select

    # Check if there's an existing mapping for this integration_user_id
    stmt = select(UserIntegrationMapping).where(
        UserIntegrationMapping.integration_user_id == integration_user_id,
        UserIntegrationMapping.integration_type == integration_type,
    )
    result = await db.execute(stmt)
    existing_mapping = result.scalar_one_or_none()

    if existing_mapping:
        logger.debug(
            "Found existing mapping for integration user ID",
            integration_user_id=integration_user_id,
            integration_type=integration_type.value,
            canonical_user_id=existing_mapping.user_id,
        )
        return str(existing_mapping.user_id)

    # No mapping found - cannot create canonical user without email
    logger.warning(
        "No mapping found for integration user ID and email not available",
        integration_user_id=integration_user_id,
        integration_type=integration_type.value,
    )
    return None


async def update_mapping_validation_timestamp(
    integration_user_id: str,
    integration_type: IntegrationType,
    db: AsyncSession,
    reset_attempts: bool = True,
) -> bool:
    """Update last_validated_at for an existing mapping to prevent redundant validation.

    Args:
        integration_user_id: The integration-specific user ID (e.g., Slack user ID)
        integration_type: The integration type
        db: Database session
        reset_attempts: If True, reset validation_attempts to 0 and clear errors.
                       If False, only update last_validated_at (for validation flows).

    Returns:
        bool: True if mapping was found and updated, False otherwise
    """
    try:
        stmt = select(UserIntegrationMapping).where(
            UserIntegrationMapping.integration_user_id == integration_user_id,
            UserIntegrationMapping.integration_type == integration_type,
        )
        result = await db.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping:
            mapping.last_validated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            if reset_attempts:
                mapping.validation_attempts = 0  # type: ignore[assignment]
                mapping.last_validation_error = None  # type: ignore[assignment]
            await db.commit()
            logger.debug(
                "Updated validation timestamp",
                integration_user_id=integration_user_id,
                integration_type=integration_type.value,
                reset_attempts=reset_attempts,
            )
            return True
        return False
    except Exception as e:
        logger.debug(
            "Could not update validation timestamp",
            integration_user_id=integration_user_id,
            integration_type=integration_type.value,
            error=str(e),
        )
        return False


async def resolve_user_id_from_email(
    email_address: str,
    integration_type: IntegrationType,
    db: Any,
    integration_specific_id: Optional[str] = None,
    created_by: str = "system",
) -> str:
    """Resolve canonical user_id from email address, checking for existing mappings and maintaining user identity.

    This function:
    1. Checks for integration-specific mapping first
    2. If not found, checks if email exists in any other integration mapping
    3. If found, reuses existing canonical user_id and creates mapping with integration_specific_id
    4. If not found, creates new canonical user and mapping with integration_specific_id

    Args:
        email_address: The user's email address
        integration_type: The integration type to create mapping for (e.g., EMAIL, SLACK)
        db: Database session to use for queries
        integration_specific_id: The integration-specific ID to store in integration_user_id
            (e.g., Slack user ID). If None, uses email_address.
        created_by: Identifier for who is creating this mapping

    Returns:
        str: The canonical user_id (UUID as string)
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
            canonical_user_id=integration_mapping.user_id,
            integration_user_id=integration_mapping.integration_user_id,
        )
        # Return the canonical user_id (UUID)
        return str(integration_mapping.user_id)

    # Check if email exists in any other integration mapping
    # This handles the case where a user already has a mapping via another integration
    stmt = select(UserIntegrationMapping).where(
        UserIntegrationMapping.user_email == email_address
    )
    result = await db.execute(stmt)
    existing_mapping = result.scalars().first()

    if existing_mapping:
        # User already exists via another integration - reuse canonical user_id
        canonical_user_id = str(existing_mapping.user_id)
        integration_id = (
            integration_specific_id
            if integration_specific_id is not None
            else email_address
        )
        logger.info(
            "Found existing mapping for email from another integration, creating mapping with same canonical user_id",
            email_address=email_address,
            integration_type=integration_type.value,
            existing_integration_type=existing_mapping.integration_type.value,
            canonical_user_id=canonical_user_id,
            integration_specific_id=integration_id,
        )
        # Create mapping using existing canonical user_id
        await store_user_mapping(
            user_email=email_address,
            integration_user_id=integration_id,
            integration_type=integration_type,
            created_by=created_by,
            canonical_user_id=canonical_user_id,
        )
        return canonical_user_id

    # No mapping found - create new canonical user and mapping
    integration_id = (
        integration_specific_id
        if integration_specific_id is not None
        else email_address
    )
    logger.info(
        "No mapping found for email, creating new canonical user and mapping",
        email_address=email_address,
        integration_type=integration_type.value,
        integration_specific_id=integration_id,
    )
    # store_user_mapping will create the canonical user if needed
    canonical_user_id = await store_user_mapping(
        user_email=email_address,
        integration_user_id=integration_id,
        integration_type=integration_type,
        created_by=created_by,
    )
    return canonical_user_id
