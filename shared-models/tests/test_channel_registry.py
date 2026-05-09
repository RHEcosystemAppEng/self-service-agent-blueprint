"""CHANNEL_REGISTRY completeness and derived ticket-type sets."""

from shared_models.channel_behavior import (
    PER_TICKET_CHANNEL_BEHAVIOR_SEED,
    ChannelBehaviorPolicy,
    DeliveryBinding,
    SessionScope,
    code_default_channel_behavior,
)
from shared_models.channel_registry import (
    CHANNEL_REGISTRY,
    PER_TICKET_BEHAVIOR,
    get_channel_definition,
    is_per_ticket_integration,
    is_ticket_delivery_integration,
    per_ticket_integration_types,
    ticket_delivery_integration_types,
)
from shared_models.models import IntegrationType


def test_registry_covers_every_integration_type() -> None:
    for it in IntegrationType:
        defn = get_channel_definition(it)
        assert defn.integration_type == it


def test_registry_matches_enum_keys() -> None:
    assert set(CHANNEL_REGISTRY.keys()) == set(IntegrationType)


def test_zammad_per_ticket_template_matches_seed() -> None:
    policy = code_default_channel_behavior(IntegrationType.ZAMMAD)
    expected = ChannelBehaviorPolicy.model_validate(PER_TICKET_CHANNEL_BEHAVIOR_SEED)
    assert policy == expected
    assert policy == PER_TICKET_BEHAVIOR


def test_ticket_types_derived_from_registry() -> None:
    assert IntegrationType.ZAMMAD in per_ticket_integration_types()
    assert IntegrationType.ZAMMAD in ticket_delivery_integration_types()
    assert is_per_ticket_integration(IntegrationType.ZAMMAD)
    assert is_ticket_delivery_integration(IntegrationType.ZAMMAD)
    assert not is_per_ticket_integration(IntegrationType.SLACK)
    assert IntegrationType.SLACK not in ticket_delivery_integration_types()


def test_zammad_ticket_user_id_suffix_flag() -> None:
    assert get_channel_definition(IntegrationType.ZAMMAD).ticket_user_id_suffix is True
    assert get_channel_definition(IntegrationType.WEB).ticket_user_id_suffix is False


def test_per_user_channels_use_standard_binding() -> None:
    for it in (
        IntegrationType.WEB,
        IntegrationType.SLACK,
        IntegrationType.TEAMS,
        IntegrationType.DISCORD,
    ):
        b = get_channel_definition(it).behavior
        assert b.session_scope == SessionScope.PER_USER
        assert b.delivery_binding == DeliveryBinding.STANDARD
