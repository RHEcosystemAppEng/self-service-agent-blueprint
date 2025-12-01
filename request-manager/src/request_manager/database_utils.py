"""Database utility functions for Request Manager."""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def create_request_log_entry_unified(
    request_id: str,
    session_id: str,
    user_id: str,
    content: str,
    request_type: str,
    integration_type: str,
    integration_context: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    set_pod_name: bool = True,
) -> None:
    """Create RequestLog entry for any API type.

    Args:
        set_pod_name: If True, set pod_name for requests that wait for responses (request-manager endpoints).
                     If False, don't set pod_name (e.g., CloudEvent requests from integration-dispatcher).
    """
    try:
        from shared_models.models import RequestLog

        # Get pod name for tracking which pod initiated the request (only for requests that wait for responses)
        pod_name = None
        if set_pod_name:
            from .communication_strategy import get_pod_name

            pod_name = get_pod_name()

        # Create RequestLog entry
        request_log = RequestLog(
            request_id=request_id,
            session_id=session_id,
            request_type=request_type,
            request_content=content,
            normalized_request={
                "user_id": user_id,
                "integration_type": (
                    integration_type.value
                    if hasattr(integration_type, "value")
                    else str(integration_type)
                ),
                "content": content,
                "request_type": request_type,
                "integration_context": integration_context or {},
            },
            agent_id=None,  # Will be set by Agent Service
            processing_time_ms=None,  # Will be set by Agent Service
            response_content=None,  # Will be set by Agent Service
            response_metadata=None,  # Will be set by Agent Service
            cloudevent_id=None,  # Will be set when CloudEvent is sent
            cloudevent_type=None,  # Will be set when CloudEvent is sent
            completed_at=None,  # Will be set by Agent Service
            pod_name=pod_name,  # Track which pod initiated this request
        )

        if db:
            db.add(request_log)
            await db.commit()
        else:
            # For backward compatibility with existing code that doesn't pass db
            from shared_models import get_database_manager

            db_manager = get_database_manager()
            async with db_manager.get_session() as session:
                session.add(request_log)
                await session.commit()

        from shared_models import configure_logging

        logger = configure_logging("request-manager")

        logger.debug(
            "RequestLog entry created",
            request_id=request_id,
            session_id=session_id,
            request_type=request_type,
        )

    except Exception as e:
        from shared_models import configure_logging

        logger = configure_logging("request-manager")

        logger.warning(
            "Failed to create RequestLog entry",
            request_id=request_id,
            request_type=request_type,
            error=str(e),
        )
        # Don't raise exception - RequestLog creation failure shouldn't stop request processing


async def try_claim_event_for_processing(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    event_source: str,
    processed_by: str,
) -> bool:
    """Atomically claim an event for processing (check-and-set pattern).

    This provides 100% guarantee against duplicate processing by using
    database unique constraint as a distributed lock.

    Returns:
        True if this pod successfully claimed the event (can process it)
        False if another pod already claimed it (must skip processing)
    """
    from shared_models import DatabaseUtils

    return await DatabaseUtils.try_claim_event_for_processing(
        db, event_id, event_type, event_source, processed_by
    )


async def record_processed_event(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    event_source: str,
    request_id: Optional[str],
    session_id: Optional[str],
    processed_by: str,
    processing_result: str,
    error_message: Optional[str] = None,
) -> None:
    """Record that an event has been processed to prevent duplicate processing.

    Note: For atomic claiming, use try_claim_event_for_processing first.
    This function updates the event record after processing completes.
    """
    from shared_models import DatabaseUtils

    await DatabaseUtils.update_processed_event(
        db,
        event_id,
        request_id=request_id,
        session_id=session_id,
        processing_result=processing_result,
        error_message=error_message,
    )


async def cleanup_old_sessions(
    db: AsyncSession,
    user_id: str,
    integration_type: Optional[str] = None,
) -> int:
    """Clean up duplicate sessions for a user, keeping only the most recent one.

    Session expiration is handled separately via the expires_at field and timeoutHours configuration.
    This function only handles duplicate cleanup when multiple active sessions exist.

    Args:
        db: Database session
        user_id: User ID to clean up sessions for
        integration_type: Integration type to filter by. If None, cleans up across all integration types.

    Returns:
        Number of sessions deactivated
    """
    from datetime import datetime, timezone

    from shared_models import configure_logging
    from shared_models.models import RequestSession, SessionStatus
    from sqlalchemy import select, update

    logger = configure_logging("request-manager")

    try:
        # Find all active sessions for the user
        where_conditions = [
            RequestSession.user_id == user_id,
            RequestSession.status == SessionStatus.ACTIVE.value,
        ]

        # Optionally filter by integration type
        if integration_type is not None:
            where_conditions.append(RequestSession.integration_type == integration_type)

        stmt = (
            select(RequestSession)
            .where(*where_conditions)
            .order_by(RequestSession.last_request_at.desc())
        )

        result = await db.execute(stmt)
        all_sessions = result.scalars().all()

        if len(all_sessions) <= 1:
            return 0  # No cleanup needed - only one or zero sessions

        # Find sessions to deactivate (keep only the most recent one)
        sessions_to_deactivate = []
        for i, session in enumerate(all_sessions):
            if i >= 1:  # Keep the first (most recent) session, deactivate the rest
                sessions_to_deactivate.append(session.session_id)

        if not sessions_to_deactivate:
            return 0

        # Deactivate old sessions
        deactivate_where_conditions = [
            RequestSession.session_id.in_(sessions_to_deactivate),
            RequestSession.user_id == user_id,
        ]

        # Optionally filter by integration type in deactivate statement
        if integration_type is not None:
            deactivate_where_conditions.append(
                RequestSession.integration_type == integration_type
            )

        deactivate_stmt = (
            update(RequestSession)
            .where(*deactivate_where_conditions)
            .values(
                status=SessionStatus.INACTIVE.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

        result = await db.execute(deactivate_stmt)
        await db.commit()

        logger.info(
            "Cleaned up duplicate sessions",
            user_id=user_id,
            integration_type=integration_type if integration_type else "all",
            deactivated_count=len(sessions_to_deactivate),
            deactivated_session_ids=sessions_to_deactivate,
        )

        return len(sessions_to_deactivate)

    except Exception as e:
        logger.error(
            "Failed to cleanup old sessions",
            user_id=user_id,
            integration_type=integration_type if integration_type else "all",
            error=str(e),
        )
        return 0


async def delete_inactive_sessions(
    db: AsyncSession,
    older_than_days: int = 30,
) -> int:
    """Delete inactive sessions older than specified days.

    Args:
        db: Database session
        older_than_days: Delete inactive sessions older than this many days (default: 30)

    Returns:
        Number of sessions deleted
    """
    from datetime import datetime, timedelta, timezone

    from shared_models import configure_logging
    from shared_models.models import RequestSession, SessionStatus
    from sqlalchemy import delete

    logger = configure_logging("request-manager")

    try:
        # Calculate cutoff time
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        # Delete inactive sessions older than cutoff
        stmt = delete(RequestSession).where(
            RequestSession.status == SessionStatus.INACTIVE.value,
            RequestSession.updated_at < cutoff_time,
        )

        result = await db.execute(stmt)
        deleted_count = result.rowcount
        await db.commit()

        logger.info(
            "Deleted inactive sessions",
            deleted_count=deleted_count,
            older_than_days=older_than_days,
            cutoff_time=cutoff_time.isoformat(),
        )

        return deleted_count

    except Exception as e:
        logger.error(
            "Failed to delete inactive sessions",
            error=str(e),
            older_than_days=older_than_days,
        )
        await db.rollback()
        return 0


async def expire_old_sessions(
    db: AsyncSession,
) -> int:
    """Expire sessions that have passed their expiration time.

    Args:
        db: Database session

    Returns:
        Number of sessions expired
    """
    from datetime import datetime, timezone

    from shared_models import configure_logging
    from shared_models.models import RequestSession, SessionStatus
    from sqlalchemy import update

    logger = configure_logging("request-manager")

    try:
        now = datetime.now(timezone.utc)

        # Expire active sessions that have passed their expiration time
        stmt = (
            update(RequestSession)
            .where(
                RequestSession.status == SessionStatus.ACTIVE.value,
                RequestSession.expires_at.isnot(None),
                RequestSession.expires_at <= now,
            )
            .values(
                status=SessionStatus.INACTIVE.value,
                updated_at=now,
            )
        )

        result = await db.execute(stmt)
        expired_count = result.rowcount
        await db.commit()

        if expired_count > 0:
            logger.info(
                "Expired old sessions",
                expired_count=expired_count,
            )

        return expired_count

    except Exception as e:
        logger.error(
            "Failed to expire old sessions",
            error=str(e),
        )
        await db.rollback()
        return 0
