"""Wired ingress/handlers must be registered; enum-only types may exist without wiring."""

from shared_models.channel_registry import (
    CHANNEL_REGISTRY,
    WIRED_DISPATCHER_HANDLER_TYPES,
    WIRED_DISPATCHER_ONLY,
    WIRED_REQUEST_MANAGER_INGRESS_TYPES,
    WIRED_RM_AND_DISPATCHER,
    WIRED_RM_INGRESS_ONLY,
    get_channel_definition,
    is_ticket_delivery_eligible,
    ticket_delivery_eligible_types,
)
from shared_models.models import IntegrationType


def test_wired_dispatcher_handlers_have_registry_entries() -> None:
    for it in WIRED_DISPATCHER_HANDLER_TYPES:
        defn = get_channel_definition(it)
        assert defn.integration_type == it


def test_wired_request_manager_ingress_has_registry_entries() -> None:
    for it in WIRED_REQUEST_MANAGER_INGRESS_TYPES:
        defn = get_channel_definition(it)
        assert defn.integration_type == it


def test_wired_unions_and_disjoint() -> None:
    assert (
        WIRED_REQUEST_MANAGER_INGRESS_TYPES
        == WIRED_RM_AND_DISPATCHER | WIRED_RM_INGRESS_ONLY
    )
    assert (
        WIRED_DISPATCHER_HANDLER_TYPES
        == WIRED_RM_AND_DISPATCHER | WIRED_DISPATCHER_ONLY
    )
    assert not (WIRED_RM_AND_DISPATCHER & WIRED_RM_INGRESS_ONLY)
    assert not (WIRED_RM_AND_DISPATCHER & WIRED_DISPATCHER_ONLY)
    assert not (WIRED_RM_INGRESS_ONLY & WIRED_DISPATCHER_ONLY)


def test_wired_set_membership() -> None:
    """Each type lives in exactly one wiring bucket (update when adding a channel)."""
    assert WIRED_RM_AND_DISPATCHER == frozenset(
        {
            IntegrationType.SLACK,
            IntegrationType.EMAIL,
            IntegrationType.ZAMMAD,
        }
    )
    assert WIRED_RM_INGRESS_ONLY == frozenset(
        {
            IntegrationType.WEB,
            IntegrationType.CLI,
            IntegrationType.TOOL,
        }
    )
    assert WIRED_DISPATCHER_ONLY == frozenset(
        {
            IntegrationType.WEBHOOK,
            IntegrationType.TEST,
        }
    )


def test_teams_discord_registered_but_not_wired() -> None:
    assert IntegrationType.TEAMS in CHANNEL_REGISTRY
    assert IntegrationType.DISCORD in CHANNEL_REGISTRY
    assert IntegrationType.TEAMS not in WIRED_REQUEST_MANAGER_INGRESS_TYPES
    assert IntegrationType.TEAMS not in WIRED_DISPATCHER_HANDLER_TYPES


def test_ticket_delivery_eligible_requires_wired_dispatcher_handler() -> None:
    assert is_ticket_delivery_eligible(IntegrationType.ZAMMAD)
    assert IntegrationType.ZAMMAD in ticket_delivery_eligible_types()
    assert not is_ticket_delivery_eligible(IntegrationType.WEB)
