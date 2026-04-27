"""Zammad ticket MCP"""

import functools
import json
from contextlib import asynccontextmanager
from datetime import datetime
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


def _calculate_laptop_age(purchase_date_str: str) -> str:
    """Calculate laptop age in years and months from a YYYY-MM-DD purchase date."""
    try:
        from datetime import datetime

        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        current_date = datetime.now()
        years = current_date.year - purchase_date.year
        months = current_date.month - purchase_date.month
        if current_date.day < purchase_date.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12
        if years == 0:
            return f"{months} month{'s' if months != 1 else ''}"
        elif months == 0:
            return f"{years} year{'s' if years != 1 else ''}"
        else:
            return f"{years} year{'s' if years != 1 else ''} and {months} month{'s' if months != 1 else ''}"
    except (ValueError, TypeError):
        return "Unable to calculate age (invalid date format)"


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
def mark_as_agent_managed_laptop_refresh(
    ctx: Context[Any, Any], dummy_parameter: str = ""
) -> str:
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
def mark_as_general_agent_managed(
    ctx: Context[Any, Any], dummy_parameter: str = ""
) -> str:
    """Tag this ticket for agent-managed general support."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    tag = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.general_agent_managed_tag
    call_basher_tool("zammad_add_ticket_tag", {"ticket_id": ticket_id, "tag": tag})

    owner = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.general_specialist_owner
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
def close(ctx: Context[Any, Any], dummy_parameter: str = "") -> str:
    """Close the ticket."""
    _, ticket_id, _ = _authorize_ticket(ctx)
    state = zammad_mcp_settings.ZAMMAD_MCP_SETTINGS.state_closed
    call_basher_tool("zammad_update_ticket", {"ticket_id": ticket_id, "state": state})
    return f"Ticket {ticket_id} moved to state {state!r}."


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def escalate_for_human_review(ctx: Context[Any, Any], dummy_parameter: str = "") -> str:
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
def send_to_manager_review(ctx: Context[Any, Any], dummy_parameter: str = "") -> str:
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
def route_to_human_managed_queue(
    ctx: Context[Any, Any], dummy_parameter: str = ""
) -> str:
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


@mcp.tool()
@_handle_tool_errors
@trace_mcp_tool()
def get_employee_laptop_info(
    ctx: Context[Any, Any],
    dummy_parameter: str = "",
) -> str:
    """Get laptop information for an employee using their authoritative user ID from request headers.

    Reads laptop data from the employee's Zammad user profile (current_laptop field)
    and returns it in a formatted string identical to the ServiceNow MCP server output.

    Args:
        dummy_parameter: Optional parameter as validation fails unless there is at least one parameter

    Returns:
        A formatted multi-line string containing the following information:
        - Employee Name: Full name of the employee
        - Employee Location: Geographic region (EMEA, LATAM, APAC, etc.)
        - Laptop Model: Brand and model of the laptop
        - Laptop Serial Number: Unique serial number
        - Laptop Purchase Date: Date when laptop was purchased (YYYY-MM-DD format)
        - Laptop Age: Calculated age in years and months from purchase date to current date
        - Laptop Warranty Expiry Date: When the warranty expires (YYYY-MM-DD format)
        - Laptop Warranty: Current warranty status (Active/Expired)
    """
    email, _ticket_id, cust_uid = _authorize_ticket(ctx)
    user = fetch_zammad_customer_user_rest(cust_uid)

    logger.info(
        "Getting laptop info from Zammad user profile",
        tool="get_employee_laptop_info",
        authoritative_user_id=email,
    )

    current_laptop_raw = user.get("current_laptop")
    if not current_laptop_raw:
        raise ValueError(
            f"No laptop data found for user {email}. "
            "Ensure the 'current_laptop' field is populated on the Zammad user profile."
        )

    laptop = json.loads(current_laptop_raw)

    purchase_date = laptop.get("purchase_date", "N/A")
    warranty_expiry = laptop.get("warranty_expiry", "N/A")

    laptop_age = _calculate_laptop_age(purchase_date)

    warranty_status = "Unknown"
    if warranty_expiry and warranty_expiry != "N/A":
        try:
            expiry_date = datetime.strptime(warranty_expiry, "%Y-%m-%d")
            warranty_status = "Active" if expiry_date > datetime.now() else "Expired"
        except ValueError:
            pass

    result = f"""
Employee Name: {laptop.get("name", "N/A")}
Employee Location: {laptop.get("location", "N/A")}
Laptop Model: {laptop.get("laptop_model", "N/A")}
Laptop Serial Number: {laptop.get("serial_number", "N/A")}
Laptop Purchase Date: {purchase_date}
Laptop Age: {laptop_age}
Laptop Warranty Expiry Date: {warranty_expiry}
Laptop Warranty: {warranty_status}
"""

    logger.info(
        "Returning laptop info for employee",
        tool="get_employee_laptop_info",
        authoritative_user_id=email,
    )

    return result


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
