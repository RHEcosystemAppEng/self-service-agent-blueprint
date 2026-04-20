"""Sync Basher calls: MCP client is async-only, so each tool runs ``asyncio.run`` on a worker thread."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from shared_models import configure_logging
from zammad_mcp.settings import ZAMMAD_MCP_SETTINGS

logger = configure_logging("zammad-mcp-basher")

_executor = ThreadPoolExecutor(
    max_workers=ZAMMAD_MCP_SETTINGS.basher_mcp_max_workers,
    thread_name_prefix="zammad-basher-mcp",
)


def _format_tool_result(result: CallToolResult) -> str:
    text = " ".join(
        block.text for block in result.content if isinstance(block, TextContent)
    ).strip()
    if result.isError:
        raise RuntimeError(text or "unknown error")
    return text or "(no content)"


async def _call_tool_async(url: str, name: str, arguments: dict[str, Any]) -> str:
    t = ZAMMAD_MCP_SETTINGS.mcp_timeout_seconds
    timeout = httpx.Timeout(t, read=t)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        async with streamable_http_client(
            url, http_client=http_client, terminate_on_close=False
        ) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return _format_tool_result(result)


def call_basher_tool(name: str, params: dict[str, Any]) -> str:
    """Invoke Basher tool name; params is wrapped as MCP arguments {"params": params}."""
    url = ZAMMAD_MCP_SETTINGS.basher_mcp_url
    arguments: dict[str, Any] = {"params": params}

    def _run() -> str:
        try:
            return asyncio.run(_call_tool_async(url, name, arguments))
        except BaseException as e:
            detail = f"tool={name!r} url={url!r}: {type(e).__name__}: {e}"
            logger.exception("Basher MCP call failed: %s", detail)
            raise RuntimeError(f"Basher MCP failed: {detail}") from e

    return _executor.submit(_run).result(
        timeout=ZAMMAD_MCP_SETTINGS.mcp_timeout_seconds
    )


def _basher_json_object(raw: str, *, what: str) -> Dict[str, Any]:
    """Parse Basher ``response_format=json`` tool output as a JSON object dict."""
    s = raw.strip()
    if not s:
        raise ValueError(
            f"Basher {what}: empty output (expected response_format=json)."
        )
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Basher {what}: invalid JSON (expected response_format=json)."
        ) from e
    if not isinstance(obj, dict):
        raise ValueError(
            f"Basher {what}: expected JSON object, got {type(obj).__name__}."
        )
    return obj


def get_user_id_by_email(email: str) -> int:
    """Resolve user id from Basher zammad_search_users (JSON); exact email match."""
    q = email.strip()
    want = q.lower()
    raw = call_basher_tool(
        "zammad_search_users",
        {
            "query": q,
            "page": 1,
            "per_page": 25,
            "response_format": "json",
        },
    )
    data = _basher_json_object(raw, what="zammad_search_users")
    items = data.get("items")
    rows: list[Any] = items if isinstance(items, list) else []
    logger.info(
        "user search (Basher)",
        email=email,
        result_count=len(rows),
    )
    for u in rows:
        if not isinstance(u, dict):
            continue
        if str(u.get("email") or "").strip().lower() == want:
            uid = int(u["id"])
            logger.info("resolved user id", email=email, user_id=uid)
            return uid
    raise ValueError(f"No Zammad user found with email {email!r}.")


def assert_ticket_customer_matches_basher(ticket_id: int, expected_email: str) -> int:
    """Confirm the ticket's customer matches ``expected_email`` using Basher only; return customer user id."""
    q = expected_email.strip()
    want = q.lower()

    def _em(u: Dict[str, Any]) -> str:
        return str(u.get("email") or "").strip().lower()

    def _mismatch(extra: str) -> ValueError:
        return ValueError(
            "Ticket customer does not match AUTHORITATIVE_USER_ID email " + extra
        )

    try:
        raw = call_basher_tool(
            "zammad_get_ticket",
            {
                "ticket_id": ticket_id,
                "include_articles": False,
                "article_limit": 0,
                "article_offset": 0,
                "response_format": "json",
            },
        )
        ticket = _basher_json_object(raw, what="zammad_get_ticket")
    except RuntimeError as e:
        raise ValueError(f"Basher MCP: {type(e).__name__}: {e}") from e
    except ValueError as e:
        raise ValueError(
            f"Basher zammad_get_ticket JSON for ticket {ticket_id}: {e}"
        ) from e

    cust = ticket.get("customer") if isinstance(ticket.get("customer"), dict) else None
    if cust and cust.get("id") is not None:
        em_c = _em(cust)
        if em_c and em_c != want:
            raise _mismatch(f"({em_c!r} vs {want!r}).")
        uid = int(cust["id"])
        if not em_c:
            resolved = get_user_id_by_email(q)
            if resolved != uid:
                raise _mismatch(f"(user id {resolved} vs ticket customer id {uid}).")
        return uid
    if ticket.get("customer_id") is not None:
        uid = int(ticket["customer_id"])
        resolved = get_user_id_by_email(q)
        if resolved != uid:
            raise _mismatch(f"(user id {resolved} vs ticket customer id {uid}).")
        return uid
    raise ValueError(f"Ticket {ticket_id} has no customer; cannot authorize.")
