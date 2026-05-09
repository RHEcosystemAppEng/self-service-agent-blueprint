"""Session resolution helpers driven by channel behavior policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .channel_behavior import (
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    SessionScope,
    build_integration_metadata_with_policy,
    effective_entry_agent_id,
    policy_from_integration_metadata,
    resolve_channel_behavior,
    should_filter_sessions_by_integration_type,
)
from .logging import configure_logging
from .models import IntegrationType, RequestSession, SessionStatus
from .session_manager import BaseSessionManager, get_or_create_ticket_session
from .session_schemas import SessionCreate, SessionResponse
from .utils import get_enum_value, json_value_as_dict

logger = configure_logging("shared-models.channel_behavior_session")


class SessionPinScopeMismatchError(ChannelBehaviorValidationError):
    """Explicit session_id pin rejected (cross-scope or wrong integration type)."""


class TicketIdRequiredError(ChannelBehaviorValidationError):
    """PER_TICKET scope requires a valid ticket_id."""


def parse_ticket_id_value(tid_raw: Any) -> Optional[int]:
    """Parse a raw ticket_id value (int >= 1) or return None."""
    if tid_raw is None:
        return None
    try:
        tid = int(tid_raw)
    except (TypeError, ValueError):
        return None
    return tid if tid >= 1 else None


def parse_ticket_id(request: Any) -> Optional[int]:
    """Extract ticket_id from request body or metadata (duck-typed)."""
    tid_raw = getattr(request, "ticket_id", None)
    if tid_raw is None:
        md = getattr(request, "metadata", None) or {}
        tid_raw = md.get("ticket_id")
    return parse_ticket_id_value(tid_raw)


def parse_ticket_id_from_metadata(metadata: Optional[dict[str, Any]]) -> Optional[int]:
    md = metadata or {}
    return parse_ticket_id_value(md.get("ticket_id"))


def row_excluded_from_unified_pool(session: RequestSession) -> bool:
    """Whether this session row must not be reused by unified PER_USER lookup."""
    pol = policy_from_integration_metadata(
        json_value_as_dict(session.integration_metadata)
    )
    if pol is None:
        logger.warning(
            "session excluded from unified pool: missing _channel_behavior snapshot",
            session_id=session.session_id,
            integration_type=get_enum_value(session.integration_type),
        )
        return True
    return (
        pol.exclude_from_unified_session_pool
        or pol.session_scope == SessionScope.PER_TICKET
    )


async def validate_explicit_session_pin(
    db: AsyncSession,
    *,
    canonical_user_id: str,
    provided_session_id: str,
    inbound_integration_type: Any,
    inbound_policy: ChannelBehaviorPolicy,
) -> RequestSession:
    """Load and validate explicit metadata.session_id reuse (§3.2.1)."""
    stmt = select(RequestSession).where(
        RequestSession.session_id == provided_session_id,
        RequestSession.user_id == canonical_user_id,
        RequestSession.status == SessionStatus.ACTIVE.value,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise SessionPinScopeMismatchError(
            f"session_id {provided_session_id!r} not found or not active for user"
        )

    now = datetime.now(timezone.utc)
    if row.expires_at is not None and row.expires_at <= now:
        raise SessionPinScopeMismatchError(
            f"session_id {provided_session_id!r} is expired"
        )

    inbound_it = get_enum_value(inbound_integration_type)
    row_it = get_enum_value(row.integration_type)
    if inbound_it != row_it:
        raise SessionPinScopeMismatchError(
            f"session pin integration_type mismatch: inbound {inbound_it!r}, row {row_it!r}"
        )

    row_policy = policy_from_integration_metadata(
        json_value_as_dict(row.integration_metadata)
    )
    if row_policy is None:
        raise SessionPinScopeMismatchError(
            "pinned session is missing _channel_behavior snapshot"
        )
    ticket_row = row_policy.session_scope == SessionScope.PER_TICKET

    if ticket_row and inbound_policy.session_scope != SessionScope.PER_TICKET:
        raise SessionPinScopeMismatchError(
            "cannot pin non-ticket traffic to a ticket-scoped session"
        )

    if (
        row_excluded_from_unified_pool(row)
        and inbound_policy.session_scope == SessionScope.PER_USER
        and not inbound_policy.exclude_from_unified_session_pool
    ):
        raise SessionPinScopeMismatchError(
            "cannot pin unified-pool traffic to an isolated session"
        )

    return row


async def touch_active_session(
    db: AsyncSession, session: RequestSession
) -> SessionResponse:
    session.last_request_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    await db.commit()
    return SessionResponse.model_validate(session)


async def prepare_new_session_metadata(
    db: AsyncSession,
    integration_type: Any,
    client_metadata: Optional[dict[str, Any]],
) -> tuple[ChannelBehaviorPolicy, dict[str, Any], str]:
    """Resolve policy, build metadata snapshot, return entry agent id."""
    policy = await resolve_channel_behavior(integration_type, db)
    meta = build_integration_metadata_with_policy(client_metadata, policy)
    return policy, meta, effective_entry_agent_id(policy)


def should_filter_lookup_by_integration_type(
    policy: Optional[ChannelBehaviorPolicy] = None,
) -> bool:
    """Solo pool per integration_type: env or inbound ``session_isolated_by_integration_type``."""
    return should_filter_sessions_by_integration_type(policy)


async def find_active_per_user_sessions(
    db: AsyncSession,
    *,
    canonical_user_id: str,
    integration_type: Any,
    filter_by_integration_type: bool,
    for_update: bool = False,
    limit: Optional[int] = None,
) -> list[RequestSession]:
    """Active PER_USER pool candidates (excludes isolated/ticket rows in unified mode)."""
    now = datetime.now(timezone.utc)
    where = [
        RequestSession.user_id == canonical_user_id,
        RequestSession.status == SessionStatus.ACTIVE.value,
        ((RequestSession.expires_at.is_(None)) | (RequestSession.expires_at > now)),
    ]
    if filter_by_integration_type:
        where.append(RequestSession.integration_type == integration_type)
    else:
        scope = func.coalesce(
            RequestSession.integration_metadata.op("->")("_channel_behavior").op("->>")(
                "session_scope"
            ),
            "",
        )
        where.append(scope != SessionScope.PER_TICKET.value)

    stmt = (
        select(RequestSession)
        .where(*where)
        .order_by(RequestSession.last_request_at.desc())
    )
    if for_update:
        stmt = stmt.with_for_update(skip_locked=True)
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if not filter_by_integration_type:
        rows = [r for r in rows if not row_excluded_from_unified_pool(r)]
    return rows


async def resolve_ticket_scoped_session(
    db: AsyncSession,
    *,
    integration_type: IntegrationType,
    canonical_user_id: str,
    ticket_id: int,
    channel_id: Optional[str],
    thread_id: Optional[str],
    integration_metadata: Optional[dict[str, Any]],
    user_context: Optional[dict[str, Any]],
    expires_at: datetime,
) -> SessionResponse:
    """PER_TICKET session (stable ``{integration_type}-{ticket_id}`` id)."""
    return await get_or_create_ticket_session(
        db,
        integration_type=integration_type,
        canonical_user_id=canonical_user_id,
        ticket_id=ticket_id,
        channel_id=channel_id,
        thread_id=thread_id,
        integration_metadata=integration_metadata or {},
        user_context=user_context or {},
        expires_at=expires_at,
    )


async def create_per_user_session_direct(
    db: AsyncSession,
    *,
    canonical_user_id: str,
    integration_type: Any,
    channel_id: Optional[str],
    thread_id: Optional[str],
    client_metadata: Optional[dict[str, Any]],
    user_context: Optional[dict[str, Any]],
    expires_at: Optional[datetime] = None,
) -> SessionResponse:
    """Create a new session row with channel behavior snapshot (direct DB, no eventing)."""
    _, merged_metadata, _ = await prepare_new_session_metadata(
        db, integration_type, client_metadata
    )
    manager = BaseSessionManager(db)
    session_data = SessionCreate(
        user_id=canonical_user_id,
        integration_type=integration_type,
        channel_id=channel_id,
        thread_id=thread_id,
        external_session_id=None,
        explicit_session_id=None,
        integration_metadata=merged_metadata,
        user_context=user_context or {},
    )
    created = await manager.create_session(session_data)
    if expires_at is not None:
        from sqlalchemy import update as sql_update

        await db.execute(
            sql_update(RequestSession)
            .where(RequestSession.session_id == created.session_id)
            .values(expires_at=expires_at)
        )
        await db.commit()
        refreshed = await manager.get_session(created.session_id)
        if refreshed is not None:
            return refreshed
    return created
