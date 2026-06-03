"""Tests for channel behavior policy resolution and metadata merge."""

import os

import pytest
from shared_models.channel_behavior import (
    CHANNEL_BEHAVIOR_SNAPSHOT_KEY,
    PER_TICKET_CHANNEL_BEHAVIOR_SEED,
    ChannelBehaviorPolicy,
    ChannelBehaviorValidationError,
    SessionScope,
    build_integration_metadata_with_policy,
    code_default_channel_behavior,
    effective_entry_agent_id,
    is_per_ticket_integration,
    per_ticket_integration_types,
    resolve_channel_behavior_sync,
    strip_reserved_channel_metadata,
    validate_channel_behavior_policy,
)
from shared_models.models import IntegrationType


def test_code_default_per_ticket_channel_zammad() -> None:
    """Registered PER_TICKET types match PER_TICKET_CHANNEL_BEHAVIOR_SEED (registry)."""
    policy = code_default_channel_behavior(IntegrationType.ZAMMAD)
    expected = ChannelBehaviorPolicy.model_validate(PER_TICKET_CHANNEL_BEHAVIOR_SEED)
    assert policy == expected
    assert IntegrationType.ZAMMAD in per_ticket_integration_types()
    assert is_per_ticket_integration(IntegrationType.ZAMMAD)


def test_code_default_web_uses_router_entry() -> None:
    os.environ["DEFAULT_AGENT_ID"] = "routing-agent"
    policy = resolve_channel_behavior_sync(IntegrationType.WEB)
    assert policy.session_scope == SessionScope.PER_USER
    assert effective_entry_agent_id(policy) == "routing-agent"
    assert policy.allow_return_to_router is True


def test_v1_router_must_match_default() -> None:
    policy = ChannelBehaviorPolicy(
        entry_agent_id="routing-agent",
        router_agent_id="other-router",
    )
    with pytest.raises(ChannelBehaviorValidationError, match="router_agent_id"):
        validate_channel_behavior_policy(policy)


def test_unknown_agent_rejected() -> None:
    policy = ChannelBehaviorPolicy(
        entry_agent_id="nonexistent-agent",
        router_agent_id="routing-agent",
    )
    with pytest.raises(ChannelBehaviorValidationError, match="allowlist"):
        validate_channel_behavior_policy(policy)


def test_strip_and_merge_metadata() -> None:
    policy = code_default_channel_behavior(IntegrationType.SLACK)
    client = {
        "thread_id": "t1",
        CHANNEL_BEHAVIOR_SNAPSHOT_KEY: {"hijack": True},
        "_channel_evil": 1,
    }
    clean = strip_reserved_channel_metadata(client)
    assert CHANNEL_BEHAVIOR_SNAPSHOT_KEY not in clean
    assert "_channel_evil" not in clean
    assert clean["thread_id"] == "t1"

    merged = build_integration_metadata_with_policy(client, policy)
    assert merged["thread_id"] == "t1"
    assert CHANNEL_BEHAVIOR_SNAPSHOT_KEY in merged
    assert merged[CHANNEL_BEHAVIOR_SNAPSHOT_KEY]["session_scope"] == "PER_USER"
