"""Delivery binding filter and ticket-delivery integration registry."""

from unittest.mock import MagicMock

from shared_models.channel_behavior import (
    DeliveryBinding,
    filter_configs_for_delivery_binding,
    is_per_ticket_integration,
    is_ticket_delivery_integration,
    per_ticket_integration_types,
    ticket_delivery_integration_types,
)
from shared_models.models import IntegrationType


def _cfg(integration_type: IntegrationType) -> MagicMock:
    c = MagicMock()
    c.integration_type = integration_type
    return c


def test_per_ticket_registry_includes_zammad() -> None:
    types = per_ticket_integration_types()
    assert types == ticket_delivery_integration_types()
    assert IntegrationType.ZAMMAD in types
    assert is_per_ticket_integration(IntegrationType.ZAMMAD)
    assert is_ticket_delivery_integration("ZAMMAD")
    assert not is_per_ticket_integration(IntegrationType.SLACK)


def test_filter_ticket_thread_keeps_ticket_backends_only() -> None:
    configs = [
        _cfg(IntegrationType.SLACK),
        _cfg(IntegrationType.ZAMMAD),
        _cfg(IntegrationType.EMAIL),
    ]
    out = filter_configs_for_delivery_binding(
        configs, DeliveryBinding.TICKET_THREAD.value
    )
    assert [c.integration_type for c in out] == [IntegrationType.ZAMMAD]


def test_filter_standard_excludes_ticket_backends() -> None:
    configs = [
        _cfg(IntegrationType.SLACK),
        _cfg(IntegrationType.ZAMMAD),
    ]
    out = filter_configs_for_delivery_binding(configs, DeliveryBinding.STANDARD.value)
    assert IntegrationType.ZAMMAD not in [c.integration_type for c in out]
    assert IntegrationType.SLACK in [c.integration_type for c in out]


def test_filter_none_binding_treats_as_standard() -> None:
    configs = [_cfg(IntegrationType.ZAMMAD), _cfg(IntegrationType.WEB)]
    out = filter_configs_for_delivery_binding(configs, None)
    assert [c.integration_type for c in out] == [IntegrationType.WEB]
