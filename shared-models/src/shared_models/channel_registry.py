"""Code registry: per-IntegrationType channel features (session, delivery, hooks)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Final, Mapping

from .channel_policy_types import (
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    DeliveryBinding,
    SessionScope,
)
from .models import IntegrationType
from .utils import get_enum_value

# Shared PER_TICKET / TICKET_THREAD template (Zammad and future ticket backends).
PER_TICKET_BEHAVIOR = ChannelBehaviorPolicy(
    entry_agent_id="ticket-review-agent",
    router_agent_id=None,
    allow_return_to_router=False,
    session_scope=SessionScope.PER_TICKET,
    exclude_from_unified_session_pool=True,
    delivery_binding=DeliveryBinding.TICKET_THREAD,
)

PER_TICKET_CHANNEL_BEHAVIOR_SEED: Dict[str, Any] = PER_TICKET_BEHAVIOR.model_dump(
    mode="json"
)

_PER_USER_BEHAVIOR = ChannelBehaviorPolicy(
    entry_agent_id=None,
    router_agent_id=None,
    allow_return_to_router=True,
    session_scope=SessionScope.PER_USER,
    exclude_from_unified_session_pool=False,
    delivery_binding=DeliveryBinding.STANDARD,
    session_isolated_by_integration_type=False,
)

# Deployment wiring (keep in sync with RM routes and IntegrationDispatcher.handlers).
#
# RM + dispatcher: full channels — inbound normalized in request-manager, replies
# delivered through integration-dispatcher.
WIRED_RM_AND_DISPATCHER: Final[frozenset[IntegrationType]] = frozenset(
    {
        IntegrationType.SLACK,
        IntegrationType.EMAIL,
        IntegrationType.ZAMMAD,
    }
)

# RM only: generic API ingress (WEB/CLI/TOOL). Session policy applies; agent replies
# typically return on the HTTP response path, not via a dispatcher handler for that type.
WIRED_RM_INGRESS_ONLY: Final[frozenset[IntegrationType]] = frozenset(
    {
        IntegrationType.WEB,
        IntegrationType.CLI,
        IntegrationType.TOOL,
    }
)

# Dispatcher only: outbound delivery (webhooks, test harness) without a dedicated RM
# ingress route for that integration type.
WIRED_DISPATCHER_ONLY: Final[frozenset[IntegrationType]] = frozenset(
    {
        IntegrationType.WEBHOOK,
        IntegrationType.TEST,
    }
)

WIRED_REQUEST_MANAGER_INGRESS_TYPES: Final[frozenset[IntegrationType]] = (
    WIRED_RM_AND_DISPATCHER | WIRED_RM_INGRESS_ONLY
)

WIRED_DISPATCHER_HANDLER_TYPES: Final[frozenset[IntegrationType]] = (
    WIRED_RM_AND_DISPATCHER | WIRED_DISPATCHER_ONLY
)


@dataclass(frozen=True)
class ChannelDefinition:
    """Declared capabilities for an integration type (code-only source of truth)."""

    integration_type: IntegrationType
    behavior: ChannelBehaviorPolicy
    ticket_user_id_suffix: bool = False

    @property
    def requires_ticket_id_for_session(self) -> bool:
        return self.behavior.session_scope == SessionScope.PER_TICKET


def _per_user(
    integration_type: IntegrationType, **behavior_kw: Any
) -> ChannelDefinition:
    behavior = _PER_USER_BEHAVIOR.model_copy(update=behavior_kw)
    return ChannelDefinition(integration_type=integration_type, behavior=behavior)


def _build_registry() -> Dict[IntegrationType, ChannelDefinition]:
    registry: Dict[IntegrationType, ChannelDefinition] = {
        IntegrationType.SLACK: _per_user(IntegrationType.SLACK),
        IntegrationType.WEB: _per_user(IntegrationType.WEB),
        IntegrationType.CLI: _per_user(IntegrationType.CLI),
        IntegrationType.TOOL: _per_user(IntegrationType.TOOL),
        IntegrationType.EMAIL: _per_user(IntegrationType.EMAIL),
        IntegrationType.SMS: _per_user(IntegrationType.SMS),
        IntegrationType.WEBHOOK: _per_user(IntegrationType.WEBHOOK),
        IntegrationType.TEAMS: _per_user(IntegrationType.TEAMS),
        IntegrationType.DISCORD: _per_user(IntegrationType.DISCORD),
        IntegrationType.TEST: _per_user(IntegrationType.TEST),
    }
    registry[IntegrationType.ZAMMAD] = ChannelDefinition(
        integration_type=IntegrationType.ZAMMAD,
        behavior=PER_TICKET_BEHAVIOR.model_copy(deep=True),
        ticket_user_id_suffix=True,
    )
    return registry


CHANNEL_REGISTRY: Mapping[IntegrationType, ChannelDefinition] = _build_registry()


def get_channel_definition(integration_type: Any) -> ChannelDefinition:
    """Return registry entry; fail closed if type is not registered."""
    try:
        it = IntegrationType(get_enum_value(integration_type))
    except ValueError as exc:
        raise ChannelBehaviorValidationError(
            f"unknown integration_type {integration_type!r}"
        ) from exc
    defn = CHANNEL_REGISTRY.get(it)
    if defn is None:
        raise ChannelBehaviorValidationError(
            f"integration_type {it.value!r} is not registered in CHANNEL_REGISTRY"
        )
    return defn


def registry_behavior_for(integration_type: Any) -> ChannelBehaviorPolicy:
    """Policy template from registry (before env DEFAULT_AGENT_ID fill)."""
    return get_channel_definition(integration_type).behavior.model_copy(deep=True)


def per_ticket_integration_types() -> frozenset[IntegrationType]:
    return frozenset(
        it
        for it, defn in CHANNEL_REGISTRY.items()
        if defn.behavior.session_scope == SessionScope.PER_TICKET
    )


def ticket_delivery_integration_types() -> frozenset[IntegrationType]:
    return frozenset(
        it
        for it, defn in CHANNEL_REGISTRY.items()
        if defn.behavior.delivery_binding == DeliveryBinding.TICKET_THREAD
    )


def ticket_delivery_eligible_types() -> frozenset[IntegrationType]:
    """TICKET_THREAD in registry and a dispatcher handler is wired."""
    return frozenset(
        it
        for it in ticket_delivery_integration_types()
        if it in WIRED_DISPATCHER_HANDLER_TYPES
    )


def is_per_ticket_integration(integration_type: Any) -> bool:
    try:
        it = IntegrationType(get_enum_value(integration_type))
    except ValueError:
        return False
    return it in per_ticket_integration_types()


def is_ticket_delivery_integration(integration_type: Any) -> bool:
    try:
        it = IntegrationType(get_enum_value(integration_type))
    except ValueError:
        return False
    return it in ticket_delivery_integration_types()


def is_ticket_delivery_eligible(integration_type: Any) -> bool:
    """Registry TICKET_THREAD plus dispatcher handler (stricter than registry alone)."""
    try:
        it = IntegrationType(get_enum_value(integration_type))
    except ValueError:
        return False
    return it in ticket_delivery_eligible_types()


def channel_uses_ticket_user_id_suffix(integration_type: Any) -> bool:
    return get_channel_definition(integration_type).ticket_user_id_suffix
