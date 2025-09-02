"""Tests for shared agent utilities."""

from shared_models.agent_types import (
    create_agent_mapping,
    is_agent_name,
    is_agent_uuid,
)


def test_agent_mapping():
    """Test AgentMapping functionality."""
    mapping_data = {
        "laptop-refresh": "960a3f77-ba6a-4513-9df8-fe8a29e390b5",
        "routing-agent": "472f242b-e66f-44a4-b919-25305d40b5ea",
    }

    mapping = create_agent_mapping(mapping_data)

    # Test name to UUID conversion
    uuid = mapping.get_uuid("laptop-refresh")
    assert uuid is not None
    assert uuid == "960a3f77-ba6a-4513-9df8-fe8a29e390b5"

    # Test UUID to name conversion
    name = mapping.get_name("960a3f77-ba6a-4513-9df8-fe8a29e390b5")
    assert name is not None
    assert name == "laptop-refresh"

    # Test invalid lookups
    assert mapping.get_uuid("nonexistent-agent") is None
    assert mapping.get_name("00000000-0000-0000-0000-000000000000") is None


def test_agent_mapping_conversion():
    """Test AgentMapping conversion methods."""
    mapping_data = {
        "laptop-refresh": "960a3f77-ba6a-4513-9df8-fe8a29e390b5",
        "routing-agent": "472f242b-e66f-44a4-b919-25305d40b5ea",
    }

    mapping = create_agent_mapping(mapping_data)

    # Test convert_to_name
    name = mapping.convert_to_name("laptop-refresh")
    assert name == "laptop-refresh"

    name = mapping.convert_to_name("960a3f77-ba6a-4513-9df8-fe8a29e390b5")
    assert name == "laptop-refresh"

    # Test convert_to_uuid
    uuid = mapping.convert_to_uuid("960a3f77-ba6a-4513-9df8-fe8a29e390b5")
    assert uuid == "960a3f77-ba6a-4513-9df8-fe8a29e390b5"

    uuid = mapping.convert_to_uuid("laptop-refresh")
    assert uuid == "960a3f77-ba6a-4513-9df8-fe8a29e390b5"


def test_agent_mapping_to_dict():
    """Test AgentMapping to_dict method."""
    mapping_data = {
        "laptop-refresh": "960a3f77-ba6a-4513-9df8-fe8a29e390b5",
        "routing-agent": "472f242b-e66f-44a4-b919-25305d40b5ea",
    }

    mapping = create_agent_mapping(mapping_data)
    result_dict = mapping.to_dict()

    assert result_dict == mapping_data


def test_utility_functions():
    """Test utility functions."""
    # Test is_agent_name
    assert is_agent_name("laptop-refresh") is True
    assert is_agent_name("routing-agent") is True
    assert is_agent_name("960a3f77-ba6a-4513-9df8-fe8a29e390b5") is False
    assert is_agent_name("") is False

    # Test is_agent_uuid
    assert is_agent_uuid("960a3f77-ba6a-4513-9df8-fe8a29e390b5") is True
    assert is_agent_uuid("472f242b-e66f-44a4-b919-25305d40b5ea") is True
    assert is_agent_uuid("laptop-refresh") is False
    assert is_agent_uuid("") is False


def test_agent_mapping_invalid_data():
    """Test AgentMapping with invalid data."""
    # Test with invalid mapping (name that looks like UUID)
    invalid_mapping = {
        "960a3f77-ba6a-4513-9df8-fe8a29e390b5": "laptop-refresh",  # Reversed
    }

    # Should skip invalid entries and create empty mapping
    mapping = create_agent_mapping(invalid_mapping)
    assert len(mapping.get_all_names()) == 0
    assert len(mapping.get_all_uuids()) == 0
