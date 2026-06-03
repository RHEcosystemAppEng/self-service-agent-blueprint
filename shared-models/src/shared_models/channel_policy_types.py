"""Channel behavior policy types (no registry imports — breaks import cycles)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class SessionScope(str, Enum):
    PER_USER = "PER_USER"
    PER_TICKET = "PER_TICKET"


class DeliveryBinding(str, Enum):
    STANDARD = "STANDARD"
    TICKET_THREAD = "TICKET_THREAD"


class ChannelBehaviorPolicy(BaseModel):
    """Versioned channel behavior document (registry template or session snapshot)."""

    schema_version: int = 1
    entry_agent_id: Optional[str] = None
    router_agent_id: Optional[str] = None
    allow_return_to_router: bool = True
    session_scope: SessionScope = SessionScope.PER_USER
    exclude_from_unified_session_pool: bool = False
    delivery_binding: DeliveryBinding = DeliveryBinding.STANDARD
    # Per-channel solo pool without SESSION_PER_INTEGRATION_TYPE env.
    session_isolated_by_integration_type: bool = False

    @field_validator("entry_agent_id", "router_agent_id", mode="before")
    @classmethod
    def _strip_agent_ids(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    def model_dump_for_snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChannelBehaviorValidationError(ValueError):
    """Policy resolution or validation failed (fail closed at session create)."""
