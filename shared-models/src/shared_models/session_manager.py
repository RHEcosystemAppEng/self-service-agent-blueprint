"""Session management for shared database operations."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .channel_behavior import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    build_integration_metadata_with_policy,
    effective_entry_agent_id,
    policy_from_integration_metadata,
    resolve_channel_behavior,
    resolve_channel_behavior_sync,
)
from .logging import configure_logging
from .models import IntegrationType, RequestSession, SessionStatus
from .session_schemas import SessionCreate, SessionResponse
from .utils import get_enum_value

logger = configure_logging("shared-models")


def initial_current_agent_id_for_integration(integration_type: Any) -> str:
    """First agent id for a new session (channel behavior policy; sync, no DB).

    Request Manager and agent-service align via this value on the session row.
    Prefer resolve_channel_behavior() when a DB session is available.
    """
    policy = resolve_channel_behavior_sync(integration_type)
    return effective_entry_agent_id(policy)


class BaseSessionManager:
    """Base session management for database operations.

    This class handles core database operations for Request Manager sessions:
    - Session lifecycle (create, update, get)
    - User context and integration metadata storage
    - Current agent assignment tracking
    - Request count tracking
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize base session manager for database operations only."""
        self.db_session = db_session

    async def create_session(
        self, session_data: SessionCreate, max_retries: int = 3
    ) -> SessionResponse:
        """Create a new Request Manager session in the database.

        Handles unique constraint violations by retrying with exponential backoff.
        The partial unique index on (user_id, integration_type) where status='ACTIVE'
        applies only when the session snapshot session_scope is not PER_TICKET, so
        multiple active ticket-scoped sessions per user+integration are allowed.

        Args:
            session_data: Session creation data
            max_retries: Maximum number of retry attempts on constraint violation

        Returns:
            SessionResponse for the created or existing session

        Raises:
            IntegrityError: If retries are exhausted and constraint violation persists
        """
        for attempt in range(max_retries):
            raw_explicit = getattr(session_data, "explicit_session_id", None)
            explicit = (
                raw_explicit.strip()
                if isinstance(raw_explicit, str) and raw_explicit.strip()
                else None
            )
            session_id_value = explicit if explicit else str(uuid.uuid4())

            try:
                policy = policy_from_integration_metadata(
                    session_data.integration_metadata
                )
                if policy is None:
                    meta_in = session_data.integration_metadata or {}
                    if CHANNEL_BEHAVIOR_SNAPSHOT_KEY in meta_in:
                        logger.warning(
                            "invalid _channel_behavior on create; re-resolving policy",
                            integration_type=get_enum_value(
                                session_data.integration_type
                            ),
                        )
                    policy = await resolve_channel_behavior(
                        session_data.integration_type, self.db_session
                    )
                integration_metadata = build_integration_metadata_with_policy(
                    session_data.integration_metadata, policy
                )

                session = RequestSession(
                    session_id=session_id_value,
                    user_id=session_data.user_id,
                    integration_type=get_enum_value(session_data.integration_type),
                    channel_id=session_data.channel_id,
                    thread_id=session_data.thread_id,
                    external_session_id=session_data.external_session_id,
                    integration_metadata=integration_metadata,
                    user_context=session_data.user_context,
                    current_agent_id=effective_entry_agent_id(policy),
                    status=SessionStatus.ACTIVE.value,
                    version=0,  # Initial version for optimistic locking
                )

                self.db_session.add(session)
                await self.db_session.commit()
                await self.db_session.refresh(session)

                logger.info(
                    "Session created successfully",
                    session_id=session.session_id,
                    user_id=session_data.user_id,
                    attempt=attempt + 1,
                )
                return SessionResponse.model_validate(session)

            except IntegrityError as e:
                # Rollback the transaction after IntegrityError
                # SQLAlchemy automatically rolls back on exception, but we need to
                # explicitly rollback to clear the session state before reusing it
                await self.db_session.rollback()

                error_str = str(e).lower()
                # Concurrent create with same explicit session_id (e.g. {type}-{ticket_id})
                if "uq_request_sessions_session_id" in error_str or (
                    "unique" in error_str
                    and "session_id" in error_str
                    and explicit is not None
                ):
                    existing_same_id = await self.get_session(session_id_value)
                    if existing_same_id is not None and str(
                        existing_same_id.user_id
                    ) == str(session_data.user_id):
                        logger.info(
                            "Session already exists for explicit session_id (race)",
                            session_id=session_id_value,
                            user_id=session_data.user_id,
                        )
                        return existing_same_id
                    raise

                # Check if it's the unique constraint violation for active sessions
                if "idx_one_active_session_per_user_integration" in error_str or (
                    "unique" in error_str and "active" in error_str
                ):
                    if attempt < max_retries - 1:
                        # Wait with exponential backoff before retrying
                        wait_time = 0.1 * (2**attempt)
                        logger.warning(
                            "Unique constraint violation on session creation, retrying",
                            user_id=session_data.user_id,
                            integration_type=session_data.integration_type,
                            attempt=attempt + 1,
                            wait_time=wait_time,
                        )
                        await asyncio.sleep(wait_time)

                        # Try to get the existing active session instead
                        existing_session = await self.get_active_session(
                            session_data.user_id,
                            get_enum_value(session_data.integration_type),
                        )
                        if existing_session:
                            logger.info(
                                "Found existing active session after constraint violation",
                                session_id=existing_session.session_id,
                                user_id=session_data.user_id,
                            )
                            return SessionResponse.model_validate(existing_session)
                        # Continue to retry if no existing session found
                    else:
                        logger.error(
                            "Failed to create session after max retries",
                            user_id=session_data.user_id,
                            integration_type=session_data.integration_type,
                            error=str(e),
                        )
                        raise
                else:
                    # Not a constraint violation we handle, re-raise
                    raise

        # Should not reach here, but just in case
        raise IntegrityError(
            statement="Failed to create session",
            params=None,
            orig=Exception("Failed to create session after max retries"),
        )

    async def get_active_session(
        self, user_id: str, integration_type: Any
    ) -> Optional[RequestSession]:
        """Get an active session for a user and integration type."""
        stmt = (
            select(RequestSession)
            .where(
                RequestSession.user_id == user_id,
                RequestSession.integration_type == get_enum_value(integration_type),
                RequestSession.status == SessionStatus.ACTIVE.value,
            )
            .order_by(RequestSession.last_request_at.desc())
            .limit(1)
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session(
        self, session_id: str, for_update: bool = False
    ) -> Optional[SessionResponse]:
        """Get Request Manager session by ID from database.

        Args:
            session_id: The session ID to retrieve
            for_update: If True, use SELECT FOR UPDATE to lock the row
                       (prevents concurrent modifications)
        """
        stmt = select(RequestSession).where(RequestSession.session_id == session_id)

        if for_update:
            # Lock the row to prevent concurrent modifications
            stmt = stmt.with_for_update(skip_locked=True)

        result = await self.db_session.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            return SessionResponse.model_validate(session)
        return None

    async def update_session(
        self,
        session_id: str,
        agent_id: Optional[str] = None,
        conversation_thread_id: Optional[str] = None,
        status: Optional[Union[SessionStatus, str]] = None,
        conversation_context: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        expected_version: Optional[int] = None,
        **kwargs: Any,  # Allow additional fields via kwargs
    ) -> Optional[SessionResponse]:
        """Update Request Manager session information in database with optimistic locking.

        Uses optimistic locking via version field to prevent lost updates.
        If expected_version is provided, the update will only succeed if the
        current version matches, preventing concurrent modification conflicts.

        Args:
            session_id: The session ID to update
            agent_id: Optional agent ID to assign
            conversation_thread_id: Optional conversation thread ID
            status: Optional session status
            conversation_context: Optional conversation context dictionary
            user_context: Optional user context dictionary
            expected_version: Optional expected version number for optimistic locking.
                            If provided and version doesn't match, update fails.
            **kwargs: Additional fields to update (e.g., status as string for backward compatibility)

        Returns:
            SessionResponse if update succeeded, None if version mismatch or session not found
        """
        update_data: Dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc),
            "last_request_at": datetime.now(timezone.utc),
        }

        if agent_id is not None:
            update_data["current_agent_id"] = agent_id
        if conversation_thread_id is not None:
            update_data["conversation_thread_id"] = conversation_thread_id
        # Handle status: can be SessionStatus enum, string, or in kwargs
        if status is not None:
            # Convert to string value: SessionStatus enum has .value, strings pass through
            update_data["status"] = status.value if hasattr(status, "value") else status
        elif "status" in kwargs:
            # Backward compatibility: allow status as string in kwargs
            update_data["status"] = kwargs["status"]
        if conversation_context is not None:
            update_data["conversation_context"] = conversation_context
        if user_context is not None:
            update_data["user_context"] = user_context

        # Increment version for optimistic locking
        update_data["version"] = RequestSession.version + 1

        # Build WHERE clause with optional version check
        where_clause = RequestSession.session_id == session_id
        if expected_version is not None:
            # Only update if version matches (optimistic locking)
            where_clause = where_clause & (RequestSession.version == expected_version)

        stmt = (
            update(RequestSession)
            .where(where_clause)
            .values(**update_data)
            .returning(RequestSession)
        )

        result = await self.db_session.execute(stmt)
        await self.db_session.commit()
        updated_session = result.scalar_one_or_none()

        if updated_session:
            logger.debug(
                "Session updated successfully",
                session_id=session_id,
                new_version=updated_session.version,
            )
            return SessionResponse.model_validate(updated_session)
        else:
            if expected_version is not None:
                logger.warning(
                    "Session update failed: version mismatch or session not found",
                    session_id=session_id,
                    expected_version=expected_version,
                )
            return None

    async def increment_request_count(self, session_id: str, request_id: str) -> None:
        """Increment the request count for a session.

        Uses atomic database operations, so this is safe for concurrent access.
        Also increments version for optimistic locking consistency.
        """
        stmt = (
            update(RequestSession)
            .where(RequestSession.session_id == session_id)
            .values(
                total_requests=RequestSession.total_requests + 1,
                last_request_id=request_id,
                last_request_at=func.now(),
                updated_at=func.now(),
                version=RequestSession.version + 1,  # Increment version atomically
            )
        )

        await self.db_session.execute(stmt)
        await self.db_session.commit()


def ticket_session_id(integration_type: IntegrationType, ticket_id: int) -> str:
    """Stable session id for PER_TICKET scope (e.g. ``zammad-42`` for IntegrationType.ZAMMAD)."""
    return f"{get_enum_value(integration_type).lower()}-{ticket_id}"


async def get_or_create_ticket_session(
    db_session: AsyncSession,
    *,
    integration_type: IntegrationType,
    canonical_user_id: str,
    ticket_id: int,
    channel_id: Optional[str],
    thread_id: Optional[str],
    integration_metadata: Dict[str, Any],
    user_context: Dict[str, Any],
    expires_at: datetime,
) -> SessionResponse:
    """Resolve or create a per-ticket session (stable id ``{type}-{ticket_id}``).

    Multiple active sessions per user are allowed for ticket-scoped types
    (migration 002 partial unique index).
    """
    stable_sid = ticket_session_id(integration_type, ticket_id)
    stmt = select(RequestSession).where(RequestSession.session_id == stable_sid)
    result = await db_session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        if str(existing.user_id) != str(canonical_user_id):
            logger.error(
                "Ticket session owned by another user",
                session_id=stable_sid,
                expected_user_id=canonical_user_id,
                actual_user_id=str(existing.user_id),
            )
            raise ValueError(
                f"Session {stable_sid} is not owned by user {canonical_user_id}"
            )
        touch_values: Dict[str, Any] = {
            "last_request_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
        }
        if get_enum_value(existing.status) != SessionStatus.ACTIVE.value:
            touch_values["status"] = SessionStatus.ACTIVE.value
        upd_existing = (
            update(RequestSession)
            .where(RequestSession.session_id == stable_sid)
            .values(**touch_values)
            .returning(RequestSession)
        )
        res_touch = await db_session.execute(upd_existing)
        updated = res_touch.scalar_one_or_none()
        await db_session.commit()
        if updated is None:
            raise RuntimeError(f"Session {stable_sid} missing after touch")
        return SessionResponse.model_validate(updated)

    policy = await resolve_channel_behavior(integration_type, db_session)
    merged_metadata = build_integration_metadata_with_policy(
        integration_metadata, policy
    )

    manager = BaseSessionManager(db_session)
    session_data = SessionCreate(
        user_id=canonical_user_id,
        integration_type=integration_type,
        explicit_session_id=stable_sid,
        channel_id=channel_id,
        thread_id=thread_id,
        external_session_id=None,
        integration_metadata=merged_metadata,
        user_context=user_context,
    )
    created = await manager.create_session(session_data)

    upd = (
        update(RequestSession)
        .where(RequestSession.session_id == created.session_id)
        .values(expires_at=expires_at)
    )
    await db_session.execute(upd)
    await db_session.commit()

    refreshed = await manager.get_session(created.session_id)
    if refreshed is None:
        raise RuntimeError(f"Session {created.session_id} missing after create")
    return refreshed
