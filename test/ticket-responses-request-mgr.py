#!/usr/bin/env python3
"""
CLI chat with Request Manager via Zammad ticket articles.

Creates customer articles in Zammad (integration trigger → dispatcher → Request Manager)
and polls ``GET /api/v1/conversations`` until each turn's ``agent_response`` is available.
Conversation rows are matched by ``session_id`` ``zammad-{ticket_id}`` plus **new**
``request_id`` per turn (snapshot taken before each article) so stale replies are not reused.

Requires Zammad REST (ZAMMAD_URL, ZAMMAD_HTTP_TOKEN), Request Manager (REQUEST_MANAGER_URL),
and ``USER_ID`` (customer email).

Customer turns use ``--customer-password`` or env ``ZAMMAD_CUSTOMER_PASSWORD`` (default ``ChangeMe123!`` if
unset or blank — same as ``zammad-bootstrap`` ``DEFAULT_PASSWORD``) so ``POST /ticket_articles`` always uses
HTTP Basic as the ticket customer (integration trigger: ``ticket.customer_id`` = current user).

For generic CLI RM without Zammad, use chat-responses-request-mgr.py instead.

The ``**tokens**`` command is sent to Request Manager only (same as chat-responses-request-mgr.py /
``CLIChatClient``); it does not create a Zammad article.
"""

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable

import httpx
from shared_clients import CLIChatClient, RequestManagerClient
from shared_models.utils import normalize_zammad_rest_api_base, zammad_rest_json_headers

_HTTP_TIMEOUT = 10
_HTTP_TIMEOUT_CREATE_TICKET = 30

TRIGGER_POLL_TIMEOUT = float(os.environ.get("TRIGGER_POLL_TIMEOUT", "180"))
TRIGGER_POLL_INTERVAL = float(os.environ.get("TRIGGER_POLL_INTERVAL", "1.0"))

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")
REQUEST_MANAGER_URL = os.environ.get("REQUEST_MANAGER_URL", "http://localhost:8080")
USER_ID = os.environ.get("USER_ID", None)
AUTHORITATIVE_USER_ID = os.environ.get("AUTHORITATIVE_USER_ID", None)
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", None)
ZAMMAD_HTTP_TOKEN = os.environ.get("ZAMMAD_HTTP_TOKEN", None)

# Seeded Zammad users from zammad-bootstrap get_or_create_user (must stay in sync with bootstrap.py).
_BOOTSTRAP_DEFAULT_CUSTOMER_PASSWORD = "ChangeMe123!"

_ZAMMAD_JSON_CLIENT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

DEFAULT_TICKET_TITLE = "Laptop refresh help request"

# RM polling: limit 1 / latest session slice used by snapshot + agent_reply poll.
_RM_CONVERSATIONS_KW = {"limit": 1, "offset": 0, "include_messages": True}


def _customer_password_effective(cli_password: str | None) -> str:
    """HTTP Basic password for customer ``POST /ticket_articles`` (bootstrap default when unset/blank)."""
    if cli_password is not None:
        stripped = cli_password.strip()
        if stripped:
            return stripped
    raw = os.environ.get("ZAMMAD_CUSTOMER_PASSWORD")
    if raw is None:
        return _BOOTSTRAP_DEFAULT_CUSTOMER_PASSWORD
    stripped = raw.strip()
    return stripped if stripped else _BOOTSTRAP_DEFAULT_CUSTOMER_PASSWORD


# ---------------------------------------------------------------------------
# Zammad API helpers
# ---------------------------------------------------------------------------


def _api_v1(base_url: str) -> str:
    return normalize_zammad_rest_api_base(base_url)


def _zammad_get_state_map(base_url: str, token: str) -> dict[int, str]:
    """Return a mapping of state_id -> state name from Zammad."""
    url = f"{_api_v1(base_url)}/ticket_states"
    response = httpx.get(
        url, headers=zammad_rest_json_headers(token), timeout=_HTTP_TIMEOUT
    )
    response.raise_for_status()
    return {s["id"]: s["name"] for s in response.json()}


def _zammad_create_ticket(
    base_url: str,
    token: str,
    customer_email: str,
    title: str = DEFAULT_TICKET_TITLE,
) -> tuple[int, str]:
    """Create a Zammad ticket and return (ticket_id, ticket_number)."""
    url = f"{_api_v1(base_url)}/tickets"
    payload: dict[str, str | object] = {
        "title": title,
        "group": "Users",
        "customer": customer_email,
    }
    response = httpx.post(
        url,
        json=payload,
        headers=zammad_rest_json_headers(token),
        timeout=_HTTP_TIMEOUT_CREATE_TICKET,
    )
    response.raise_for_status()
    data = response.json()
    return data["id"], str(data["number"])


def _zammad_get_conversation_metadata(
    base_url: str, token: str, ticket_id: int, state_map: dict[int, str]
) -> tuple[str, str, str]:
    """Return the metadata of (state, owner, group) for the ticket."""
    url = f"{_api_v1(base_url)}/tickets/{ticket_id}?expand=true"
    try:
        response = httpx.get(
            url, headers=zammad_rest_json_headers(token), timeout=_HTTP_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        state_id = data.get("state_id")
        state_name = state_map.get(state_id, str(state_id))
        state = state_name
        owner = data.get("owner", {})
        if isinstance(owner, dict):
            owner_name = owner.get("fullname") or owner.get("login") or "unassigned"
        else:
            owner_name = str(owner) if owner else "unassigned"
        group = data.get("group", {})
        if isinstance(group, dict):
            group_name = group.get("name") or "none"
        else:
            group_name = str(group) if group else "none"
        return state, owner_name, group_name
    except Exception:
        return "unknown", "unknown", "unknown"


def _zammad_add_customer_article(
    base_url: str,
    ticket_id: int,
    body: str,
    *,
    from_email: str,
    customer_basic: tuple[str, str],
) -> int | None:
    """POST a customer (web) article — inbound harness traffic only; agent replies use dispatcher."""
    url = f"{_api_v1(base_url)}/ticket_articles"
    payload = {
        "ticket_id": ticket_id,
        "body": body,
        "type": "web",
        "internal": False,
        "sender": "Customer",
        "from": from_email,
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            auth=customer_basic,
            headers=_ZAMMAD_JSON_CLIENT_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        aid = data.get("id")
        return int(aid) if aid is not None else None
    except Exception as e:
        print(f"Warning: could not add article to Zammad ticket: {e}", file=sys.stderr)
        return None


def _zammad_delete_ticket(base_url: str, token: str, ticket_id: int) -> None:
    """Delete a Zammad ticket."""
    url = f"{_api_v1(base_url)}/tickets/{ticket_id}"
    httpx.delete(url, headers=zammad_rest_json_headers(token), timeout=_HTTP_TIMEOUT)


def _conversation_entries_first_session(data: dict) -> list:
    """First session's ``conversation`` list from GET /conversations-style payload."""
    sessions = data.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return []
    first = sessions[0]
    if not isinstance(first, dict):
        return []
    conv = first.get("conversation")
    return conv if isinstance(conv, list) else []


def _zammad_verify_ticket_number_logged(
    api_base: str,
    token: str,
    ticket_id: int,
    ticket_number: str,
    *,
    verbose: bool = False,
) -> None:
    """GET /tickets/{id} and log mismatch vs create response (wrong env / proxy)."""
    try:
        vurl = f"{api_base}/tickets/{ticket_id}"
        vresp = httpx.get(
            vurl, headers=zammad_rest_json_headers(token), timeout=_HTTP_TIMEOUT
        )
        vresp.raise_for_status()
        vdata = vresp.json()
        vnum = vdata.get("number")
        if str(vnum) != str(ticket_number):
            print(
                f"[zammad] warning: create said number={ticket_number!r} "
                f"but GET /tickets/{ticket_id} number={vnum!r}",
                file=sys.stderr,
            )
        elif verbose:
            print(
                f"[zammad] verified GET /tickets/{ticket_id} number={vnum!r} "
                f"title={vdata.get('title')!r}",
                file=sys.stderr,
            )
    except Exception as ex:
        print(
            f"[zammad] warning: could not verify ticket via GET: {ex}", file=sys.stderr
        )


def _request_ids_from_conversation(conv: list) -> set[str]:
    out: set[str] = set()
    for entry in conv:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("request_id")
        if rid is not None:
            out.add(str(rid))
    return out


async def _conversation_request_ids_snapshot(
    rm_client: RequestManagerClient, *, session_id: str
) -> set[str]:
    """Return existing ``request_id`` values for this RM session (before posting a new Zammad article).

    Session id is ``zammad-{ticket_id}`` and is stable for the ticket; each new turn adds a **new**
    ``request_id``. Matching on message text alone can replay an old completed row — we only accept
    rows whose ``request_id`` was **not** present in this snapshot.
    """
    try:
        data = await rm_client.get_conversations(
            session_id=session_id,
            **_RM_CONVERSATIONS_KW,
        )
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    return _request_ids_from_conversation(_conversation_entries_first_session(data))


async def _poll_conversation_for_agent_reply(
    rm_client: RequestManagerClient,
    *,
    session_id: str,
    user_message: str,
    baseline_request_ids: set[str],
    timeout_s: float,
    poll_interval_s: float,
) -> str:
    """Wait until RM exposes ``agent_response`` for this user turn (webhook-driven path).

    ``baseline_request_ids`` must be taken **before** ``POST /ticket_articles`` so the new
    RequestLog row (new ``request_id``) is not confused with prior turns on the same session.
    """
    deadline = time.monotonic() + timeout_s
    target = user_message.strip()
    interval = max(0.25, poll_interval_s)

    while time.monotonic() < deadline:
        try:
            data = await rm_client.get_conversations(
                session_id=session_id,
                **_RM_CONVERSATIONS_KW,
            )
        except Exception as ex:
            print(
                f"[rm] poll: get_conversations failed: {ex}",
                file=sys.stderr,
            )
            await asyncio.sleep(interval)
            continue

        if not isinstance(data, dict):
            await asyncio.sleep(interval)
            continue

        conv = _conversation_entries_first_session(data)
        if not conv:
            await asyncio.sleep(interval)
            continue

        for entry in reversed(conv):
            if not isinstance(entry, dict):
                continue
            um = (entry.get("user_message") or "").strip()
            if um != target:
                continue
            rid = entry.get("request_id")
            if rid is None or str(rid) in baseline_request_ids:
                continue
            ar = entry.get("agent_response")
            if ar is not None and str(ar).strip():
                return str(ar).strip()
            break

        await asyncio.sleep(interval)

    return (
        f"Timeout after {timeout_s:.0f}s waiting for agent_response "
        f"(session_id={session_id!r}; check webhook, dispatcher, RM logs)."
    )


async def _rm_tokens_cli_style(cli: CLIChatClient, *, rm_session_id: str) -> None:
    """POST ``**tokens**`` to RM generic (CLI) pinned to this ticket's RM session."""
    agent_response = await cli.send_message("**tokens**", rm_session_id=rm_session_id)
    if isinstance(agent_response, dict):
        response_content = agent_response.get("content", str(agent_response))
    else:
        response_content = agent_response
    cli._handle_tokens_command(response_content)


# ---------------------------------------------------------------------------
# Chat loop with ticket conversation metadata
# ---------------------------------------------------------------------------


async def _chat_loop_with_conversation_metadata(
    rm_client: CLIChatClient,
    send_to_agent: Callable[[str], Awaitable[str]],
    *,
    initial_message: str | None,
    ticket_id: int,
    ticket_number: str,
    zammad_base_url: str,
    zammad_token: str,
    state_map: dict[int, str],
    include_conversation_metadata: bool,
    test_mode: bool,
) -> None:
    """
    Chat loop: poll-print agent replies (Zammad delivery via integration-dispatcher only).

    The TICKET_STATUS line format is:
        TICKET_STATUS:{ticket_number}:{state}:owner={owner}:group={group}
    It is printed to stdout so callers can strip it before saving conversations.
    """

    def emit_conversation_metadata() -> None:
        if (
            include_conversation_metadata
            and ticket_id
            and zammad_base_url
            and zammad_token
        ):
            state, owner, group = _zammad_get_conversation_metadata(
                zammad_base_url, zammad_token, ticket_id, state_map
            )
            print(f"TICKET_STATUS:{ticket_number}:{state}:owner={owner}:group={group}")

    if not test_mode:
        print("CLI Chat - Type 'quit' to exit")
        print(f"Using Request Manager at: {rm_client.request_manager_url}")

    if initial_message:
        if test_mode:
            # In test mode the LLM simulator will send the first real message.
            # Don't send initial_message to the agent — the ticket body already
            # captures it. Print a placeholder so openshift_chat_client's
            # get_agent_initialization() can complete without hanging.
            print("agent: ")
            print(AGENT_MESSAGE_TERMINATOR)
        else:
            agent_response = await send_to_agent(initial_message)
            print(f"agent: {agent_response}")

    if test_mode:
        try:
            for line in sys.stdin:
                message = line.strip()
                if not message:
                    continue
                if message.lower() in ["quit", "exit"]:
                    break
                if message.lower() == "**tokens**":
                    # Harness (OpenShiftChatClient) waits for `agent:` before accepting the
                    # terminator; token formatting has no agent prefix unless we add this line.
                    print("agent: ")
                    await _rm_tokens_cli_style(
                        rm_client, rm_session_id=f"zammad-{ticket_id}"
                    )
                    print(AGENT_MESSAGE_TERMINATOR)
                    continue
                agent_response = await send_to_agent(message)
                print(f"agent: {agent_response}")
                print(AGENT_MESSAGE_TERMINATOR)
                emit_conversation_metadata()
        except (EOFError, KeyboardInterrupt):
            pass
    else:
        while True:
            try:
                message = input("> ")
                if message.lower() in ["quit", "exit", "q"]:
                    break
                if message.strip():
                    if message.lower() == "**tokens**":
                        await _rm_tokens_cli_style(
                            rm_client, rm_session_id=f"zammad-{ticket_id}"
                        )
                        continue
                    agent_response = await send_to_agent(message)
                    print(f"agent: {agent_response}")
                    emit_conversation_metadata()
            except KeyboardInterrupt:
                break

    await rm_client.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Zammad ticket chat: customer articles → webhook pipeline → poll conversations for replies "
            "(requires ZAMMAD_URL, ZAMMAD_HTTP_TOKEN, REQUEST_MANAGER_URL)."
        )
    )
    parser.add_argument("--user-id", help="User ID for the chat session")
    parser.add_argument("--request-manager-url", help="Request Manager URL")
    parser.add_argument(
        "--initial-message", help="Initial message to send to the agent"
    )
    parser.add_argument(
        "--ticket-title",
        default=DEFAULT_TICKET_TITLE,
        help=f"Title for the created Zammad ticket (default: '{DEFAULT_TICKET_TITLE}')",
    )
    parser.add_argument(
        "--delete-ticket-on-exit",
        action="store_true",
        help="Delete the Zammad ticket when the session ends",
    )
    parser.add_argument(
        "--include-conversation_metadata",
        action="store_true",
        help="Emit a TICKET_STATUS line after each agent response",
    )
    parser.add_argument(
        "--customer-password",
        default=None,
        help=(
            "Customer Zammad login password for customer articles (HTTP Basic). "
            "Uses env ZAMMAD_CUSTOMER_PASSWORD when omitted; default ChangeMe123! if env unset or blank."
        ),
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=TRIGGER_POLL_TIMEOUT,
        dest="poll_timeout",
        help=(
            "Seconds to wait per user turn for agent_response "
            f"(default {TRIGGER_POLL_TIMEOUT}; env TRIGGER_POLL_TIMEOUT)."
        ),
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=TRIGGER_POLL_INTERVAL,
        dest="poll_interval",
        help=(
            "Seconds between GET /api/v1/conversations polls "
            f"(default {TRIGGER_POLL_INTERVAL}; env TRIGGER_POLL_INTERVAL)."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print Zammad diagnostic messages on stderr (REST URL hints, verify success, etc.).",
    )
    return parser


async def main() -> None:
    args = _build_arg_parser().parse_args()

    base_user_id = args.user_id or USER_ID or AUTHORITATIVE_USER_ID
    request_manager_url = args.request_manager_url or REQUEST_MANAGER_URL
    initial_message = (
        args.initial_message or "please introduce yourself and tell me how you can help"
    )

    zammad_base_url = ZAMMAD_URL
    zammad_token = ZAMMAD_HTTP_TOKEN

    if not zammad_base_url or not zammad_token:
        print(
            "error: ZAMMAD_URL and ZAMMAD_HTTP_TOKEN are required.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not base_user_id:
        print(
            "error: USER_ID or --user-id is required (customer email for the ticket).",
            file=sys.stderr,
        )
        sys.exit(2)

    api_base = _api_v1(zammad_base_url)
    if args.verbose:
        print(
            f"[zammad] ZAMMAD_URL={zammad_base_url!r} -> REST {api_base}",
            file=sys.stderr,
        )
        print(
            "[zammad] Compare the host above to the Zammad UI you open; they must be the same "
            "instance (or the same cluster entrypoint) or ticket numbers will not match the UI.",
            file=sys.stderr,
        )

    customer_pw = _customer_password_effective(args.customer_password)
    customer_basic: tuple[str, str] = (base_user_id, customer_pw)
    if args.verbose:
        print(
            "[zammad] Customer articles: HTTP Basic as ticket customer (webhook trigger path).",
            file=sys.stderr,
        )

    try:
        state_map = _zammad_get_state_map(zammad_base_url, zammad_token)
        ticket_id, ticket_number = _zammad_create_ticket(
            zammad_base_url,
            zammad_token,
            base_user_id,
            title=args.ticket_title,
        )
        print(f"Created Zammad ticket #{ticket_number} (id={ticket_id})")
        if args.verbose:
            print(
                "[zammad] Expect webhook→dispatcher→RM; replies from polling conversations API.",
                file=sys.stderr,
            )
        _zammad_verify_ticket_number_logged(
            api_base,
            zammad_token,
            ticket_id,
            ticket_number,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"error: could not create Zammad ticket: {e}", file=sys.stderr)
        sys.exit(2)

    # Append internal ticket id (not display number) to user_id for session uniqueness
    # The Zammad MCP server expects the internal id from /api/v1/tickets/{id}, not the display number
    user_id = f"{base_user_id}-{ticket_id}"

    rm = CLIChatClient(
        request_manager_url=request_manager_url,
        user_id=user_id,
    )

    async def send_to_agent(msg: str) -> str:
        session_sid = f"zammad-{ticket_id}"
        baseline_ids = await _conversation_request_ids_snapshot(
            rm, session_id=session_sid
        )
        article_id = _zammad_add_customer_article(
            zammad_base_url,
            ticket_id,
            body=msg,
            from_email=base_user_id,
            customer_basic=customer_basic,
        )
        if article_id is None:
            return "Error: could not create customer article in Zammad"
        return await _poll_conversation_for_agent_reply(
            rm,
            session_id=session_sid,
            user_message=msg,
            baseline_request_ids=baseline_ids,
            timeout_s=args.poll_timeout,
            poll_interval_s=args.poll_interval,
        )

    print(f"Using user ID: {user_id}")
    print(
        "Request Manager: poll GET /api/v1/conversations for replies (webhook-driven ingest)"
    )
    print("Using LangGraph state machine for conversation management")

    try:
        await _chat_loop_with_conversation_metadata(
            rm,
            send_to_agent,
            initial_message=initial_message,
            ticket_id=ticket_id,
            ticket_number=ticket_number,
            zammad_base_url=zammad_base_url,
            zammad_token=zammad_token,
            state_map=state_map,
            include_conversation_metadata=args.include_conversation_metadata,
            test_mode=not sys.stdin.isatty(),
        )
    finally:
        if (
            args.delete_ticket_on_exit
            and ticket_id
            and zammad_base_url
            and zammad_token
        ):
            try:
                _zammad_delete_ticket(zammad_base_url, zammad_token, ticket_id)
                print(f"Deleted Zammad ticket #{ticket_number}")
            except Exception as e:
                print(f"Warning: could not delete Zammad ticket: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
