"""Request-manager ingress routes must match channel_registry wiring."""

from shared_models.channel_registry import (
    WIRED_REQUEST_MANAGER_INGRESS_TYPES,
    WIRED_RM_AND_DISPATCHER,
    WIRED_RM_INGRESS_ONLY,
)
from shared_models.models import IntegrationType

# Dedicated RM routes (main.py); WEB/CLI/TOOL use /api/v1/requests/generic.
RM_DEDICATED_ROUTE_TYPES = frozenset(
    {
        IntegrationType.SLACK,
        IntegrationType.EMAIL,
        IntegrationType.ZAMMAD,
    }
)


def test_dedicated_rm_routes_are_rm_and_dispatcher_bucket() -> None:
    assert RM_DEDICATED_ROUTE_TYPES <= WIRED_RM_AND_DISPATCHER


def test_generic_api_types_are_rm_ingress_only_bucket() -> None:
    assert WIRED_RM_INGRESS_ONLY == frozenset(
        {
            IntegrationType.WEB,
            IntegrationType.CLI,
            IntegrationType.TOOL,
        }
    )


def test_rm_ingress_wiring_covers_dedicated_and_generic() -> None:
    assert (
        WIRED_REQUEST_MANAGER_INGRESS_TYPES
        == RM_DEDICATED_ROUTE_TYPES | WIRED_RM_INGRESS_ONLY
    )
