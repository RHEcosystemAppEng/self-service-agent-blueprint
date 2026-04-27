"""Process environment for the Zammad MCP wrapper"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _str_env(name: str, default: str) -> str:
    v = os.getenv(name, default).strip()
    return v or default


def _group_env(name: str, default: str) -> str:
    """If name is in os.environ, return stripped value (may be empty); else default.

    Use when callers treat empty string as "skip" (e.g. optional group or owner email).
    ``_str_env`` cannot do that: missing and empty both collapse to the same default.
    """
    if name in os.environ:
        return os.environ[name].strip()
    return default


@dataclass(frozen=True)
class ZammadMcpSettings:
    """All configuration for this process, read once from the environment."""

    agent_managed_tag: str
    state_closed: str
    tag_escalate_human: str
    group_escalated_laptop: str
    tag_manager_review: str
    group_human_managed: str
    user_manager_field: str
    default_manager_email: str
    laptop_specialist_owner: str
    general_agent_managed_tag: str
    general_specialist_owner: str
    zammad_rest_base_url: str
    zammad_http_token: str
    basher_mcp_url: str
    basher_mcp_max_workers: int
    mcp_timeout_seconds: float
    mcp_transport: str
    mcp_listen_host: str
    mcp_listen_port: int


def load_zammad_mcp_settings() -> ZammadMcpSettings:
    """Load and validate all settings from the environment."""
    zammad_url = os.getenv("ZAMMAD_URL", "").strip()
    if not zammad_url:
        raise ValueError(
            "ZAMMAD_URL is required (set the Zammad web origin, e.g. from Helm secret zammad-url)."
        )
    zammad_http_token = os.getenv("ZAMMAD_HTTP_TOKEN", "").strip()
    if not zammad_http_token:
        raise ValueError(
            "ZAMMAD_HTTP_TOKEN is required on this process "
            "(Kubernetes secret zammad-http-token / local export)."
        )

    basher_raw = os.getenv("ZAMMAD_BASHER_MCP_URL", "").strip().rstrip("/")
    basher_mcp_url = basher_raw if basher_raw else "http://127.0.0.1:8001/mcp"

    mcp_transport = os.environ.get("MCP_TRANSPORT", "sse").strip() or "sse"
    mcp_listen_host = os.environ.get("MCP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    raw_port = (
        os.environ.get(
            "SELF_SERVICE_AGENT_ZAMMAD_MCP_SERVICE_PORT_HTTP", "8002"
        ).strip()
        or "8002"
    )
    try:
        mcp_listen_port = int(raw_port)
    except ValueError:
        mcp_listen_port = 8002

    to_raw = (os.getenv("ZAMMAD_MCP_TIMEOUT_SECONDS", "120") or "120").strip()
    try:
        mcp_timeout_seconds = max(1.0, float(to_raw))
    except ValueError as e:
        raise ValueError(
            f"Invalid ZAMMAD_MCP_TIMEOUT_SECONDS: {to_raw!r} (expected a number)."
        ) from e

    workers_raw = (os.getenv("ZAMMAD_BASHER_MCP_MAX_WORKERS", "8") or "8").strip()
    try:
        basher_mcp_max_workers = int(workers_raw)
    except ValueError as e:
        raise ValueError(
            f"Invalid ZAMMAD_BASHER_MCP_MAX_WORKERS: {workers_raw!r} (expected an integer)."
        ) from e
    basher_mcp_max_workers = max(1, min(basher_mcp_max_workers, 128))

    return ZammadMcpSettings(
        agent_managed_tag=_str_env(
            "ZAMMAD_AGENT_MANAGED_TAG", "agent-managed-laptop-refresh"
        ),
        state_closed=_str_env("ZAMMAD_STATE_CLOSED", "closed"),
        tag_escalate_human=_str_env(
            "ZAMMAD_TAG_ESCALATE_HUMAN", "escalated-human-review"
        ),
        group_escalated_laptop=_group_env(
            "ZAMMAD_GROUP_ESCALATED_LAPTOP", "escalated_laptop_refresh_tickets"
        ),
        tag_manager_review=_str_env(
            "ZAMMAD_TAG_MANAGER_REVIEW", "pending-manager-review"
        ),
        group_human_managed=_group_env(
            "ZAMMAD_GROUP_HUMAN_MANAGED", "human_managed_tickets"
        ),
        user_manager_field=_str_env("ZAMMAD_USER_MANAGER_FIELD", "manager_email"),
        default_manager_email=os.getenv("ZAMMAD_MANAGER_EMAIL", "").strip(),
        laptop_specialist_owner=_group_env(
            "ZAMMAD_LAPTOP_SPECIALIST_OWNER",
            "agent.laptop-specialist@example.com",
        ),
        general_agent_managed_tag=_str_env(
            "ZAMMAD_GENERAL_AGENT_MANAGED_TAG", "agent-managed-general-support"
        ),
        general_specialist_owner=_group_env(
            "ZAMMAD_SPECIALIST_OWNER",
            "agent.general@example.com",
        ),
        zammad_rest_base_url=zammad_url.rstrip("/"),
        zammad_http_token=zammad_http_token,
        basher_mcp_url=basher_mcp_url,
        basher_mcp_max_workers=basher_mcp_max_workers,
        mcp_timeout_seconds=mcp_timeout_seconds,
        mcp_transport=mcp_transport,
        mcp_listen_host=mcp_listen_host,
        mcp_listen_port=mcp_listen_port,
    )


ZAMMAD_MCP_SETTINGS: ZammadMcpSettings = load_zammad_mcp_settings()
