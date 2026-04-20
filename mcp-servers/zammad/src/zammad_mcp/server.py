"""Zammad ticket MCP"""

import functools
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Literal, ParamSpec, cast

from mcp.server.fastmcp import Context, FastMCP
from mcp_common.headers import header_first
from mcp_common.tracing import trace_mcp_tool
from shared_models import configure_logging
from starlette.responses import JSONResponse
from tracing_config.auto_tracing import run as auto_tracing_run
from zammad_mcp import settings as zammad_mcp_settings
from zammad_mcp.basher_client import (
    assert_ticket_customer_matches_basher,
    call_basher_tool,
    get_user_id_by_email,
)
from zammad_mcp.zammad_auth_id import parse_email_and_ticket_id
from zammad_mcp.zammad_rest_client import fetch_zammad_customer_user_rest

SERVICE_NAME = "zammad-mcp-server"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)


def _tool_error_text(exc: BaseException) -> str:
    """One-line message; flattens ExceptionGroup chains."""
    if isinstance(exc, BaseExceptionGroup):
        if len(exc.exceptions) == 1:
            return _tool_error_text(exc.exceptions[0])
        inner = "; ".join(_tool_error_text(s) for s in exc.exceptions)
        return f"{type(exc).__name__}: {inner}"
    return f"{type(exc).__name__}: {exc}"


_P = ParamSpec("_P")


def _handle_tool_errors(func: Callable[_P, str]) -> Callable[_P, str]:
    """Catch errors after trace_mcp_tool records span ERROR, then log and return text."""

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> str:
        try:
            return func(*args, **kwargs)
        except BaseExceptionGroup as eg:
            msg = f"{func.__name__} failed: {_tool_error_text(eg)}"
            logger.exception(msg)
            return msg
        except Exception as e:
            msg = f"{func.__name__} failed: {_tool_error_text(e)}"
            logger.exception(msg)
            return msg

    return wrapper


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncGenerator[None, None]:
    s = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS
    logger.info(
        "Zammad MCP wrapper configured",
        zammad_url=s.zammad_rest_base_url,
        basher_mcp_url=s.basher_mcp_url,
    )
    try:
        yield
    finally:
        logger.info("Shutting down Zammad MCP server")


mcp = FastMCP(
    "Zammad Ticket MCP",
    host=zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.mcp_listen_host,
    port=zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.mcp_listen_port,
    stateless_http=(
        zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.mcp_transport == "streamable-http"
    ),
    lifespan=lifespan,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Any) -> JSONResponse:
    return JSONResponse({"status": "OK", "service": SERVICE_NAME})


def _authorize_ticket(ctx: Context[Any, Any]) -> tuple[str, int, int]:
    """Parse ``AUTHORITATIVE_USER_ID`` and Basher-verify ticket customer; returns (email, ticket_id, customer_uid)."""
    raw = header_first(ctx, "AUTHORITATIVE_USER_ID", "authoritative_user_id")
    if not raw:
        raise ValueError(
            "AUTHORITATIVE_USER_ID missing on the MCP request (set the tool header from the agent). "
            "Expected format: {email}-{ticket_id} (Zammad internal ticket id)."
        )
    email, ticket_id = parse_email_and_ticket_id(raw)
    cust_uid = assert_ticket_customer_matches_basher(ticket_id, email)
    return email, ticket_id, cust_uid


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def mark_as_agent_managed_laptop_refresh(ctx: Context[Any, Any]) -> str:
    """Tag this ticket for agent-managed laptop refresh."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    tag = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.agent_managed_tag
    call_basher_tool("zammad_add_ticket_tag", {"ticket_id": ticket_id, "tag": tag})

    owner = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.laptop_specialist_owner
    if owner:
        get_user_id_by_email(owner)
        call_basher_tool(
            "zammad_update_ticket",
            {"ticket_id": ticket_id, "owner": owner},
        )
    parts = [f"Ticket {ticket_id} tagged as {tag!r}"]
    if owner:
        parts.append(f"owner set to {owner!r}")
    return ", ".join(parts) + "."


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def close(ctx: Context[Any, Any]) -> str:
    """Close the ticket."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    state = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.state_closed
    call_basher_tool("zammad_update_ticket", {"ticket_id": ticket_id, "state": state})
    return f"Ticket {ticket_id} moved to state {state!r}."


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def escalate_for_human_review(ctx: Context[Any, Any]) -> str:
    """Escalate this ticket to the human escalation queue."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    tag = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.tag_escalate_human
    call_basher_tool("zammad_add_ticket_tag", {"ticket_id": ticket_id, "tag": tag})

    gname = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.group_escalated_laptop
    gstrip = gname.strip()
    update: dict[str, Any] = {}
    if gstrip:
        update["group"] = gstrip
    if update:
        call_basher_tool("zammad_update_ticket", {"ticket_id": ticket_id, **update})

    gmsg = f", group {gname!r}" if gstrip else ""
    return f"Ticket {ticket_id} tagged {tag!r}{gmsg}."


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def send_to_manager_review(ctx: Context[Any, Any]) -> str:
    """Assign this ticket to the customer's manager for approval."""
    _, ticket_id, cust_uid = _authorize_ticket(ctx)
    customer_user = fetch_zammad_customer_user_rest(cust_uid)
    field = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.user_manager_field
    raw = customer_user.get(field)
    manager = (str(raw).strip() if raw is not None else "") or ""
    if not manager:
        manager = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.default_manager_email
    if not manager:
        raise ValueError(
            f"Customer has no {field!r} and ZAMMAD_MANAGER_EMAIL is unset."
        )

    tag = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.tag_manager_review
    call_basher_tool("zammad_add_ticket_tag", {"ticket_id": ticket_id, "tag": tag})

    get_user_id_by_email(manager)
    call_basher_tool(
        "zammad_update_ticket",
        {"ticket_id": ticket_id, "owner": manager},
    )
    return f"Ticket {ticket_id} assigned to {manager!r}, tag {tag!r}."


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def route_to_human_managed_queue(ctx: Context[Any, Any]) -> str:
    """Route this ticket to the human-managed queue."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    gname = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.group_human_managed
    gstrip = gname.strip()
    if gstrip:
        call_basher_tool(
            "zammad_update_ticket",
            {"ticket_id": ticket_id, "group": gstrip},
        )
    gmsg = f"group {gname!r}" if gstrip else "no group change"
    return f"Ticket {ticket_id} routed to {gmsg}."


def main() -> None:
    mcp.run(
        transport=cast(
            Literal["stdio", "sse", "streamable-http"],
            zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.mcp_transport,
        )
    )


app = mcp.streamable_http_app()


if __name__ == "__main__":
    main()
