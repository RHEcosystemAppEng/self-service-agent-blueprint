"""Delivery context enrichment from session snapshots."""

import pytest
from shared_models.channel_behavior import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    ChannelBehaviorPolicy,
    DeliveryBinding,
    SessionScope,
    build_integration_metadata_with_policy,
    delivery_context_for_forward,
    delivery_context_from_session_metadata,
    looks_like_per_ticket_session_id,
    policy_from_integration_metadata,
)


def test_delivery_context_from_ticket_snapshot() -> None:
    pol = ChannelBehaviorPolicy(
        session_scope=SessionScope.PER_TICKET,
        delivery_binding=DeliveryBinding.TICKET_THREAD,
    )
    meta = build_integration_metadata_with_policy({}, pol)
    assert delivery_context_from_session_metadata(meta) == {
        "delivery_binding": "TICKET_THREAD"
    }


def test_delivery_context_empty_without_snapshot() -> None:
    assert delivery_context_from_session_metadata({}) == {}
    assert delivery_context_from_session_metadata(None) == {}


def test_looks_like_per_ticket_session_id() -> None:
    assert looks_like_per_ticket_session_id("zammad-42") is True
    assert looks_like_per_ticket_session_id("web-uuid-here") is False
    assert looks_like_per_ticket_session_id("not-a-ticket") is False


def test_delivery_context_for_forward_logs_ticket_shaped_without_binding(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        ctx = delivery_context_for_forward(
            session_id="zammad-99",
            integration_metadata={},
        )
    assert ctx == {}
    assert any("missing delivery_binding" in r.message for r in caplog.records)


def test_policy_from_integration_metadata_rejects_invalid_snapshot() -> None:
    meta = {CHANNEL_BEHAVIOR_SNAPSHOT_KEY: {"session_scope": "NOT_A_SCOPE"}}
    assert policy_from_integration_metadata(meta) is None


def test_policy_from_integration_metadata_parses_valid_snapshot() -> None:
    pol = ChannelBehaviorPolicy(session_scope=SessionScope.PER_USER)
    meta = build_integration_metadata_with_policy({}, pol)
    parsed = policy_from_integration_metadata(meta)
    assert parsed is not None
    assert parsed.session_scope == SessionScope.PER_USER
