"""Shared utilities for canonical user ID resolution.

This module provides functions for resolving email addresses and other identifiers
to canonical user_id (UUID) values. These functions are used across all services
to ensure consistent user identity.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import configure_logging
from .models import User, UserIntegrationMapping

logger = configure_logging("shared_models")


def is_uuid(user_id: str) -> bool:
    """Check if a string looks like a UUID.

    Args:
        user_id: The string to check

    Returns:
        True if the string matches UUID pattern, False otherwise
    """
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    return bool(uuid_pattern.match(user_id))


async def _ensure_email_mapping(
    canonical_user_id: str, email_address: str, db: AsyncSession
) -> None:
    """Ensure a UserIntegrationMapping exists for an email address.

    This is a helper function to maintain consistency - ensures that when we create
    a canonical user from an email, we also create the corresponding mapping entry.

    Args:
        canonical_user_id: The canonical user_id (UUID)
        email_address: The email address
        db: Database session
    """
    from .models import IntegrationType

    stmt = (
        select(UserIntegrationMapping)
        .where(
            UserIntegrationMapping.user_id == canonical_user_id,
            UserIntegrationMapping.integration_type == IntegrationType.EMAIL,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    existing_mapping = result.scalar_one_or_none()

    if not existing_mapping:
        # Create a mapping entry for the email (using email as integration_user_id for EMAIL type)
        insert_stmt = insert(UserIntegrationMapping).values(
            user_id=canonical_user_id,
            user_email=email_address,
            integration_type=IntegrationType.EMAIL,
            integration_user_id=email_address,  # For EMAIL, integration_user_id is the email itself
            last_validated_at=datetime.now(timezone.utc),
            validation_attempts=0,
            last_validation_error=None,
            created_by="user_utils",
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["user_id", "integration_type"],
            set_={
                "user_email": insert_stmt.excluded.user_email,
                "integration_user_id": insert_stmt.excluded.integration_user_id,
                "last_validated_at": insert_stmt.excluded.last_validated_at,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(upsert_stmt)
        await db.commit()

        logger.debug(
            "Created UserIntegrationMapping for email",
            canonical_user_id=canonical_user_id,
            email=email_address,
        )


async def get_or_create_canonical_user(email_address: str, db: AsyncSession) -> str:
    """Get or create a canonical user_id for an email address.

    This function uses a "try-create, catch-duplicate" pattern to handle race conditions.
    If two concurrent requests try to create a user with the same email, one will succeed
    and the other will catch the unique constraint violation and retry the lookup.

    Args:
        email_address: The user's email address
        db: Database session

    Returns:
        str: The canonical user_id (UUID as string)
    """
    # First, try to find existing user by email in mappings
    # This is the most reliable source since mappings are created first
    stmt = (
        select(UserIntegrationMapping)
        .where(UserIntegrationMapping.user_email == email_address)
        .limit(1)
    )
    result = await db.execute(stmt)
    existing_mapping = result.scalar_one_or_none()

    if existing_mapping:
        canonical_user_id = str(existing_mapping.user_id)
        # Ensure EMAIL mapping exists (the existing mapping might be for a different integration type)
        await _ensure_email_mapping(canonical_user_id, email_address, db)
        return canonical_user_id

    # Check if User exists with this primary_email
    stmt = select(User).where(User.primary_email == email_address)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # Ensure EMAIL mapping exists even if user already exists
        await _ensure_email_mapping(str(existing_user.user_id), email_address, db)
        return str(existing_user.user_id)

    # Try to create new User
    # If another concurrent request creates it first, we'll catch the unique constraint
    # violation and retry the lookup
    try:
        new_user_id = str(uuid.uuid4())
        new_user = User(
            user_id=new_user_id,
            primary_email=email_address,
        )
        db.add(new_user)
        await db.flush()  # Flush to get the user_id

        logger.info(
            "Created new canonical user",
            user_id=new_user_id,
            primary_email=email_address,
        )

        # Ensure EMAIL mapping exists for the new user
        await _ensure_email_mapping(new_user_id, email_address, db)

        return new_user_id
    except Exception as e:
        # If we get a unique constraint violation (or any error), retry the lookup
        # This handles the race condition where another request created the user
        # between our check and our insert
        error_str = str(e).lower()
        if (
            "unique" in error_str
            or "duplicate" in error_str
            or "constraint" in error_str
        ):
            logger.debug(
                "User creation failed due to unique constraint, retrying lookup",
                email_address=email_address,
                error=str(e),
            )
            # Retry lookup - another request likely created it
            stmt = select(User).where(User.primary_email == email_address)
            result = await db.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                logger.info(
                    "Found user created by concurrent request",
                    user_id=existing_user.user_id,
                    primary_email=email_address,
                )
                # Ensure EMAIL mapping exists
                await _ensure_email_mapping(
                    str(existing_user.user_id), email_address, db
                )
                return str(existing_user.user_id)

        # If it's not a unique constraint error, or we still can't find the user, re-raise
        logger.error(
            "Error creating canonical user",
            email_address=email_address,
            error=str(e),
        )
        raise


async def resolve_canonical_user_id(
    user_id: str,
    integration_type: Optional[Any] = None,
    db: Optional[AsyncSession] = None,
) -> str:
    """Resolve user_id to canonical user_id (UUID) if it's an email address.

    This function checks if the user_id is already a UUID. If it is, it verifies
    the user exists in the users table and creates it if it doesn't. If not a UUID,
    it assumes it's an email address and resolves it to a canonical user_id.

    Args:
        user_id: The user_id from the request (may be email or UUID)
        integration_type: Optional integration type (for logging/debugging)
        db: Database session (required if user_id is not a UUID, or to verify UUID exists)

    Returns:
        str: Canonical user_id (UUID as string)

    Raises:
        ValueError: If user_id is not a UUID and db is not provided
    """
    # Check if user_id looks like a UUID
    if is_uuid(user_id):
        # Already a UUID, but we need to verify it exists in the users table
        # This handles cases where a UUID is provided but doesn't exist yet (e.g., test scripts)
        if db is not None:
            stmt = select(User).where(User.user_id == user_id)
            result = await db.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                # User exists, return as-is
                return user_id
            else:
                # UUID provided but user doesn't exist - create it
                # This is useful for test scripts or cases where UUID is generated client-side
                logger.info(
                    "UUID provided but user doesn't exist, creating user",
                    user_id=user_id,
                    integration_type=(
                        (
                            integration_type.value
                            if hasattr(integration_type, "value")
                            else str(integration_type)
                        )
                        if integration_type
                        else None
                    ),
                )
                try:
                    new_user = User(
                        user_id=user_id,
                        primary_email=None,  # No email for UUID-only users
                    )
                    db.add(new_user)
                    await db.flush()
                    logger.info(
                        "Created user for provided UUID",
                        user_id=user_id,
                    )
                    return user_id
                except Exception as e:
                    # If creation fails (e.g., concurrent creation), try to fetch again
                    error_str = str(e).lower()
                    if (
                        "unique" in error_str
                        or "duplicate" in error_str
                        or "constraint" in error_str
                    ):
                        logger.debug(
                            "User creation failed, retrying lookup",
                            user_id=user_id,
                            error=str(e),
                        )
                        stmt = select(User).where(User.user_id == user_id)
                        result = await db.execute(stmt)
                        existing_user = result.scalar_one_or_none()
                        if existing_user:
                            return user_id
                    raise
        else:
            # UUID provided but no db session - assume it exists (for backward compatibility)
            # This maintains the old behavior when db is not provided
            return user_id

    # Looks like an email address, resolve to canonical user_id
    if db is None:
        raise ValueError(
            "Database session required to resolve email address to canonical user_id"
        )

    logger.warning(
        "Received email address as user_id, resolving to canonical user_id",
        email_address=user_id,
        integration_type=integration_type,
    )

    try:
        # get_or_create_canonical_user now ensures EMAIL mapping exists
        canonical_user_id = await get_or_create_canonical_user(user_id, db)

        logger.info(
            "Resolved email to canonical user_id",
            email_address=user_id,
            canonical_user_id=canonical_user_id,
            integration_type=(
                (
                    integration_type.value
                    if hasattr(integration_type, "value")
                    else str(integration_type)
                )
                if integration_type
                else None
            ),
        )

        return canonical_user_id
    except Exception as e:
        logger.error(
            "Failed to resolve email to canonical user_id",
            email_address=user_id,
            error=str(e),
        )
        raise
