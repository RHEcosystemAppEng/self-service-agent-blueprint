"""Simple agent identifier utilities - shared across all services."""

import re
from typing import Dict, Optional

# UUID pattern for validation
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def is_agent_uuid(identifier: str) -> bool:
    """Check if a string is an agent UUID."""
    return bool(identifier and UUID_PATTERN.match(identifier))


def is_agent_name(identifier: str) -> bool:
    """Check if a string is an agent name (not a UUID)."""
    return bool(identifier and not is_agent_uuid(identifier))


class AgentMapping:
    """Simple agent name to UUID mapping with conversion utilities."""

    def __init__(self, mapping: Dict[str, str]):
        """Initialize with a dictionary mapping agent names to UUIDs."""
        self._name_to_uuid: Dict[str, str] = {}
        self._uuid_to_name: Dict[str, str] = {}

        for name, uuid in mapping.items():
            if is_agent_name(name) and is_agent_uuid(uuid):
                self._name_to_uuid[name] = uuid
                self._uuid_to_name[uuid] = name

    def get_uuid(self, name: str) -> Optional[str]:
        """Get UUID for an agent name."""
        return self._name_to_uuid.get(name)

    def get_name(self, uuid: str) -> Optional[str]:
        """Get name for an agent UUID."""
        return self._uuid_to_name.get(uuid)

    def convert_to_name(self, identifier: str) -> Optional[str]:
        """Convert a string to agent name if it's a name, or look up the name if it's a UUID."""
        if is_agent_name(identifier):
            return identifier
        elif is_agent_uuid(identifier):
            return self.get_name(identifier)
        return None

    def convert_to_uuid(self, identifier: str) -> Optional[str]:
        """Convert a string to agent UUID if it's a UUID, or look up the UUID if it's a name."""
        if is_agent_uuid(identifier):
            return identifier
        elif is_agent_name(identifier):
            return self.get_uuid(identifier)
        return None

    def get_all_names(self) -> list[str]:
        """Get all agent names."""
        return list(self._name_to_uuid.keys())

    def get_all_uuids(self) -> list[str]:
        """Get all agent UUIDs."""
        return list(self._uuid_to_name.keys())

    def to_dict(self) -> Dict[str, str]:
        """Convert back to a dictionary for API responses."""
        return self._name_to_uuid.copy()


def create_agent_mapping(agents_dict: Dict[str, str]) -> AgentMapping:
    """Create an AgentMapping from a dictionary."""
    return AgentMapping(agents_dict)
