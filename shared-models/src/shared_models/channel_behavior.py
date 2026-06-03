"""Channel behavior policy: per-integration session, routing, and delivery semantics."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, Final, Mapping, Optional, Sequence, Set

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .channel_policy_types import (
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    DeliveryBinding,
    SessionScope,
)
from .logging import configure_logging
from .models import IntegrationDefaultConfig, IntegrationType
from .utils import get_enum_value, json_value_as_dict

logger = configure_logging("shared-models")

# System-owned key on RequestSession.integration_metadata (never from clients).
CHANNEL_BEHAVIOR_SNAPSHOT_KEY: Final[str] = "_channel_behavior"
_RESERVED_CHANNEL_METADATA_PREFIX: Final[str] = "_channel_"

# Blueprint agent ids (config/agents/*.yaml). Override via AGENT_ID_ALLOWLIST env.
_DEFAULT_AGENT_ID_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "routing-agent",
        "ticket-review-agent",
        "ticket-general-agent",
        "ticket-laptop-refresh-agent",
        "laptop-refresh-agent",
    }
)


def default_router_agent_id() -> str:
    return os.getenv("DEFAULT_AGENT_ID", "routing-agent").strip() or "routing-agent"


def session_per_integration_type_enabled() -> bool:
    return os.getenv("SESSION_PER_INTEGRATION_TYPE", "false").lower() == "true"


def get_agent_id_allowlist() -> Set[str]:
    raw = os.getenv("AGENT_ID_ALLOWLIST", "").strip()
    if raw:
        return {a.strip() for a in raw.split(",") if a.strip()}
    return set(_DEFAULT_AGENT_ID_ALLOWLIST)


def channel_behavior_allow_db_override() -> bool:
    """When true, merge integration_default_configs.config.channel_behavior over registry."""
    return os.getenv("CHANNEL_BEHAVIOR_ALLOW_DB_OVERRIDE", "false").lower() == "true"


def _merge_policy_dict(
    base: ChannelBehaviorPolicy, overrides: Optional[Mapping[str, Any]]
) -> ChannelBehaviorPolicy:
    if not overrides:
        return base
    data = base.model_dump()
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    return ChannelBehaviorPolicy.model_validate(data)


@lru_cache(maxsize=1)
def _channel_behavior_overrides_from_env() -> Dict[str, Dict[str, Any]]:
    """Parse CHANNEL_BEHAVIOR_OVERRIDES JSON (deploy-time env on request-manager)."""
    raw = os.getenv("CHANNEL_BEHAVIOR_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("invalid CHANNEL_BEHAVIOR_OVERRIDES JSON", error=str(exc))
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "CHANNEL_BEHAVIOR_OVERRIDES must be a JSON object keyed by integration type"
        )
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[str(key).strip().upper()] = value
    return out


def load_channel_behavior_env_override(
    integration_type: Any,
) -> Optional[Dict[str, Any]]:
    """Partial policy from CHANNEL_BEHAVIOR_OVERRIDES for this integration type."""
    it = get_enum_value(integration_type).upper()
    blob = _channel_behavior_overrides_from_env().get(it)
    return blob if isinstance(blob, dict) else None


async def load_channel_behavior_from_db(
    integration_type: Any,
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Load config.channel_behavior from integration_default_configs when override enabled."""
    it = IntegrationType(get_enum_value(integration_type))
    stmt = select(IntegrationDefaultConfig).where(
        IntegrationDefaultConfig.integration_type == it
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if not row or not row.config:
        return None
    cfg = json_value_as_dict(row.config)
    blob = cfg.get("channel_behavior")
    return blob if isinstance(blob, dict) else None


def _apply_env_default_agent_ids(
    policy: ChannelBehaviorPolicy,
) -> ChannelBehaviorPolicy:
    router = default_router_agent_id()
    updates: Dict[str, Any] = {}
    if policy.router_agent_id is None:
        updates["router_agent_id"] = router
    if policy.entry_agent_id is None:
        updates["entry_agent_id"] = router
    if not updates:
        return policy
    return policy.model_copy(update=updates)


def validate_channel_behavior_policy(policy: ChannelBehaviorPolicy) -> None:
    """Fail closed on unknown agents or v1 router constraint."""
    allowlist = get_agent_id_allowlist()
    router_default = default_router_agent_id()

    if policy.router_agent_id and policy.router_agent_id != router_default:
        raise ChannelBehaviorValidationError(
            f"router_agent_id must equal DEFAULT_AGENT_ID ({router_default!r}) in v1; "
            f"got {policy.router_agent_id!r}"
        )

    for field_name in ("entry_agent_id", "router_agent_id"):
        agent_id = getattr(policy, field_name)
        if agent_id and agent_id not in allowlist:
            raise ChannelBehaviorValidationError(
                f"{field_name} {agent_id!r} is not in the deployed agent allowlist"
            )


def _resolve_from_registry(integration_type: Any) -> ChannelBehaviorPolicy:
    from .channel_registry import registry_behavior_for

    return registry_behavior_for(integration_type)


def code_default_channel_behavior(integration_type: Any) -> ChannelBehaviorPolicy:
    """Policy template from CHANNEL_REGISTRY (alias for registry resolution)."""
    return _resolve_from_registry(integration_type)


def _finalize_policy(policy: ChannelBehaviorPolicy) -> ChannelBehaviorPolicy:
    resolved = _apply_env_default_agent_ids(policy)
    validate_channel_behavior_policy(resolved)
    return resolved


async def resolve_channel_behavior(
    integration_type: Any,
    db: Optional[AsyncSession] = None,
) -> ChannelBehaviorPolicy:
    """Resolve: registry → env overrides → optional DB override → agent ids → validate."""
    base = _resolve_from_registry(integration_type)
    base = _merge_policy_dict(
        base, load_channel_behavior_env_override(integration_type)
    )
    if channel_behavior_allow_db_override() and db is not None:
        db_blob = await load_channel_behavior_from_db(integration_type, db)
        base = _merge_policy_dict(base, db_blob)
    return _finalize_policy(base)


def resolve_channel_behavior_sync(integration_type: Any) -> ChannelBehaviorPolicy:
    """Resolve from registry + CHANNEL_BEHAVIOR_OVERRIDES env (no DB)."""
    base = _resolve_from_registry(integration_type)
    base = _merge_policy_dict(
        base, load_channel_behavior_env_override(integration_type)
    )
    return _finalize_policy(base)


def _config_integration_type(config: Any) -> IntegrationType:
    it = getattr(config, "integration_type", None)
    if isinstance(it, IntegrationType):
        return it
    return IntegrationType(get_enum_value(it))


def filter_configs_for_delivery_binding(
    configs: Sequence[Any],
    delivery_binding: Optional[str],
) -> list[Any]:
    """Keep configs that may deliver for STANDARD vs TICKET_THREAD binding."""
    from .channel_registry import ticket_delivery_eligible_types

    binding = (delivery_binding or DeliveryBinding.STANDARD.value).strip()
    ticket_types = ticket_delivery_eligible_types()
    if binding == DeliveryBinding.TICKET_THREAD.value:
        return [c for c in configs if _config_integration_type(c) in ticket_types]
    return [c for c in configs if _config_integration_type(c) not in ticket_types]


def strip_reserved_channel_metadata(
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Remove system-owned keys from client metadata before merge."""
    if not metadata:
        return {}
    return {
        k: v
        for k, v in metadata.items()
        if not (
            k == CHANNEL_BEHAVIOR_SNAPSHOT_KEY
            or (isinstance(k, str) and k.startswith(_RESERVED_CHANNEL_METADATA_PREFIX))
        )
    }


def build_integration_metadata_with_policy(
    client_metadata: Optional[Dict[str, Any]],
    policy: ChannelBehaviorPolicy,
) -> Dict[str, Any]:
    """Merge client metadata then apply server snapshot (server wins on reserved keys)."""
    clean = strip_reserved_channel_metadata(client_metadata)
    out = dict(clean)
    out[CHANNEL_BEHAVIOR_SNAPSHOT_KEY] = policy.model_dump_for_snapshot()
    return out


def looks_like_per_ticket_session_id(session_id: str) -> bool:
    """True for stable ids ``{integration_type}-{ticket_id}`` (e.g. ``zammad-42``)."""
    sid = (session_id or "").strip()
    prefix, sep, suffix = sid.rpartition("-")
    if not sep or not prefix or not suffix:
        return False
    try:
        return int(suffix) >= 1
    except ValueError:
        return False


def delivery_context_from_session_metadata(
    integration_metadata: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Fields to merge onto delivery integration_context from a session snapshot."""
    pol = policy_from_integration_metadata(integration_metadata)
    if pol is None:
        return {}
    return {"delivery_binding": pol.delivery_binding.value}


def delivery_context_for_forward(
    *,
    session_id: Optional[str],
    integration_metadata: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Delivery fields for RM forwarder; logs error if ticket-shaped id lacks binding."""
    ctx = delivery_context_from_session_metadata(integration_metadata)
    if ctx.get("delivery_binding"):
        return ctx
    if session_id and looks_like_per_ticket_session_id(session_id):
        logger.error(
            "ticket-shaped session missing delivery_binding in snapshot",
            session_id=session_id,
        )
    return ctx


def policy_from_integration_metadata(
    integration_metadata: Optional[Dict[str, Any]],
) -> Optional[ChannelBehaviorPolicy]:
    """Parse snapshotted policy from a session row."""
    if not integration_metadata:
        return None
    blob = integration_metadata.get(CHANNEL_BEHAVIOR_SNAPSHOT_KEY)
    if not isinstance(blob, dict):
        return None
    try:
        return ChannelBehaviorPolicy.model_validate(blob)
    except ValidationError as exc:
        logger.warning(
            "invalid _channel_behavior snapshot",
            error=str(exc),
        )
        return None


def effective_entry_agent_id(policy: ChannelBehaviorPolicy) -> str:
    return policy.entry_agent_id or default_router_agent_id()


def effective_router_agent_id(policy: ChannelBehaviorPolicy) -> str:
    return policy.router_agent_id or default_router_agent_id()


def policy_allows_return_to_router(policy: ChannelBehaviorPolicy) -> bool:
    return policy.allow_return_to_router


def policy_needs_ticket_context(policy: ChannelBehaviorPolicy) -> bool:
    return bool(policy.session_scope == SessionScope.PER_TICKET)


def should_filter_sessions_by_integration_type(
    policy: Optional[ChannelBehaviorPolicy] = None,
) -> bool:
    """Unified vs solo pool: env SESSION_PER_INTEGRATION_TYPE or per-channel policy flag."""
    if policy is not None and policy.session_isolated_by_integration_type:
        return True
    return session_per_integration_type_enabled()


# Re-export registry helpers for backward-compatible imports from channel_behavior.
from .channel_registry import (  # noqa: E402
    CHANNEL_REGISTRY,
    PER_TICKET_CHANNEL_BEHAVIOR_SEED,
    WIRED_DISPATCHER_HANDLER_TYPES,
    WIRED_DISPATCHER_ONLY,
    WIRED_REQUEST_MANAGER_INGRESS_TYPES,
    WIRED_RM_AND_DISPATCHER,
    WIRED_RM_INGRESS_ONLY,
    ChannelDefinition,
    channel_uses_ticket_user_id_suffix,
    get_channel_definition,
    is_per_ticket_integration,
    is_ticket_delivery_eligible,
    is_ticket_delivery_integration,
    per_ticket_integration_types,
    ticket_delivery_eligible_types,
    ticket_delivery_integration_types,
)

__all__ = [
    "CHANNEL_BEHAVIOR_SNAPSHOT_KEY",
    "CHANNEL_REGISTRY",
    "ChannelBehaviorPolicy",
    "ChannelBehaviorValidationError",
    "ChannelDefinition",
    "DeliveryBinding",
    "PER_TICKET_CHANNEL_BEHAVIOR_SEED",
    "SessionScope",
    "build_integration_metadata_with_policy",
    "channel_behavior_allow_db_override",
    "channel_uses_ticket_user_id_suffix",
    "code_default_channel_behavior",
    "delivery_context_for_forward",
    "delivery_context_from_session_metadata",
    "effective_entry_agent_id",
    "effective_router_agent_id",
    "filter_configs_for_delivery_binding",
    "get_channel_definition",
    "is_per_ticket_integration",
    "is_ticket_delivery_eligible",
    "is_ticket_delivery_integration",
    "looks_like_per_ticket_session_id",
    "per_ticket_integration_types",
    "policy_allows_return_to_router",
    "policy_from_integration_metadata",
    "policy_needs_ticket_context",
    "resolve_channel_behavior",
    "resolve_channel_behavior_sync",
    "session_per_integration_type_enabled",
    "should_filter_sessions_by_integration_type",
    "ticket_delivery_eligible_types",
    "ticket_delivery_integration_types",
    "WIRED_RM_AND_DISPATCHER",
    "WIRED_DISPATCHER_HANDLER_TYPES",
    "WIRED_DISPATCHER_ONLY",
    "WIRED_REQUEST_MANAGER_INGRESS_TYPES",
    "WIRED_RM_INGRESS_ONLY",
    "validate_channel_behavior_policy",
]
