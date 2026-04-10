#!/usr/bin/env python3
"""
CLI chat application with Request Manager integration and Zammad ticket tracking.

Creates a Zammad ticket at session start, appends the ticket number to the
user ID for session uniqueness, and optionally reports ticket status inline
after each agent response as a strippable TICKET_STATUS line.
"""

import argparse
import asyncio
import os
import sys

import httpx
from shared_clients import CLIChatClient

AGENT_MESSAGE_TERMINATOR = os.environ.get("AGENT_MESSAGE_TERMINATOR", "")
REQUEST_MANAGER_URL = os.environ.get("REQUEST_MANAGER_URL", "http://localhost:8080")
USER_ID = os.environ.get("USER_ID", None)
AUTHORITATIVE_USER_ID = os.environ.get("AUTHORITATIVE_USER_ID", None)
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", None)
ZAMMAD_HTTP_TOKEN = os.environ.get("ZAMMAD_HTTP_TOKEN", None)


# ---------------------------------------------------------------------------
# Zammad API helpers
# ---------------------------------------------------------------------------


def _zammad_headers(token: str) -> dict:
    return {
        "Authorization": f"Token token={token}",
        "Content-Type": "application/json",
    }


def _zammad_api_base(base_url: str) -> str:
    """Normalise base_url to always end with /api/v1 (without duplication)."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/api/v1"):
        return stripped
    return f"{stripped}/api/v1"


def _zammad_get_state_map(base_url: str, token: str) -> dict[int, str]:
    """Return a mapping of state_id -> state name from Zammad."""
    url = f"{_zammad_api_base(base_url)}/ticket_states"
    response = httpx.get(url, headers=_zammad_headers(token), timeout=10)
    response.raise_for_status()
    return {s["id"]: s["name"] for s in response.json()}


DEFAULT_TICKET_TITLE = "Laptop refresh help request"


def _zammad_create_ticket(
    base_url: str, token: str, customer_email: str, title: str = DEFAULT_TICKET_TITLE
) -> tuple[int, str]:
    """Create a Zammad ticket and return (ticket_id, ticket_number)."""
    url = f"{_zammad_api_base(base_url)}/tickets"
    payload = {
        "title": title,
        "group": "Users",
        "customer": customer_email,
    }
    response = httpx.post(url, json=payload, headers=_zammad_headers(token), timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["id"], str(data["number"])


_ZAMMAD_STATE_MAP = {
    "new": "new",
    "open": "being processed by agent",
    "pending reminder": "escalated",
    "pending close": "escalated",
    "closed": "closed",
    "merged": "closed",
}


def _zammad_get_ticket_status(
    base_url: str, token: str, ticket_id: int, state_map: dict[int, str]
) -> tuple[str, str, str]:
    """Return (state, owner, group) for the ticket."""
    url = f"{_zammad_api_base(base_url)}/tickets/{ticket_id}?expand=true"
    try:
        response = httpx.get(url, headers=_zammad_headers(token), timeout=10)
        response.raise_for_status()
        data = response.json()
        state_id = data.get("state_id")
        state_name = state_map.get(state_id, str(state_id))
        state = _ZAMMAD_STATE_MAP.get(state_name.lower(), state_name)
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


def _zammad_get_user_id_by_email(base_url: str, token: str, email: str) -> int | None:
    """Look up a Zammad user ID by email address."""
    url = f"{_zammad_api_base(base_url)}/users/search?query={email}&limit=1"
    try:
        response = httpx.get(url, headers=_zammad_headers(token), timeout=10)
        response.raise_for_status()
        results = response.json()
        for user in results:
            if user.get("email", "").lower() == email.lower():
                return user["id"]
    except Exception:
        pass
    return None


def _zammad_add_article(
    base_url: str,
    token: str,
    ticket_id: int,
    body: str,
    from_email: str,
    sender: str,
    origin_by_id: int | None = None,
) -> None:
    """Add an article (message) to a Zammad ticket.

    Args:
        sender: "Customer" for user messages, "Agent" for agent responses.
        from_email: email address shown as the sender of the article.
        origin_by_id: Zammad user ID to set as the article originator,
            overriding the authenticated token owner.
    """
    url = f"{_zammad_api_base(base_url)}/ticket_articles"
    payload = {
        "ticket_id": ticket_id,
        "body": body,
        "type": "note",
        "internal": True,
        "sender": sender,
        "from": from_email,
    }
    if origin_by_id is not None:
        payload["origin_by_id"] = origin_by_id
    try:
        response = httpx.post(
            url, json=payload, headers=_zammad_headers(token), timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Warning: could not add article to Zammad ticket: {e}", file=sys.stderr)


def _zammad_delete_ticket(base_url: str, token: str, ticket_id: int) -> None:
    """Delete a Zammad ticket."""
    url = f"{_zammad_api_base(base_url)}/tickets/{ticket_id}"
    httpx.delete(url, headers=_zammad_headers(token), timeout=10)


# ---------------------------------------------------------------------------
# Chat loop with ticket status
# ---------------------------------------------------------------------------


AGENT_EMAIL = "agent.laptop-specialist@example.com"


async def _chat_loop_with_status(
    chat_client: CLIChatClient,
    *,
    initial_message: str | None,
    ticket_id: int | None,
    ticket_number: str | None,
    customer_email: str | None,
    agent_user_id: int | None,
    zammad_base_url: str | None,
    zammad_token: str | None,
    state_map: dict[int, str],
    show_ticket_status: bool,
    test_mode: bool,
) -> None:
    """
    Chat loop that records each user message and agent response as Zammad ticket
    articles and emits a TICKET_STATUS line after each agent response.

    The TICKET_STATUS line format is:
        TICKET_STATUS:{ticket_number}:{state}:owner={owner}:group={group}
    It is printed to stdout so callers can strip it before saving conversations.
    """

    def add_user_article(message: str) -> None:
        if ticket_id and zammad_base_url and zammad_token and customer_email:
            _zammad_add_article(
                zammad_base_url,
                zammad_token,
                ticket_id,
                body=message,
                from_email=customer_email,
                sender="Customer",
            )

    def add_agent_article(message: str) -> None:
        if ticket_id and zammad_base_url and zammad_token:
            _zammad_add_article(
                zammad_base_url,
                zammad_token,
                ticket_id,
                body=message,
                from_email=AGENT_EMAIL,
                sender="Agent",
                origin_by_id=agent_user_id,
            )

    def emit_status() -> None:
        if show_ticket_status and ticket_id and zammad_base_url and zammad_token:
            state, owner, group = _zammad_get_ticket_status(
                zammad_base_url, zammad_token, ticket_id, state_map
            )
            print(f"TICKET_STATUS:{ticket_number}:{state}:owner={owner}:group={group}")

    if not test_mode:
        print("CLI Chat - Type 'quit' to exit")
        print(f"Using Request Manager at: {chat_client.request_manager_url}")

    if initial_message:
        if test_mode:
            # In test mode the LLM simulator will send the first real message.
            # Don't send initial_message to the agent — the ticket body already
            # captures it. Print a placeholder so openshift_chat_client's
            # get_agent_initialization() can complete without hanging.
            print("agent: ")
            print(AGENT_MESSAGE_TERMINATOR)
        else:
            add_user_article(initial_message)
            agent_response = await chat_client.send_message(initial_message)
            add_agent_article(str(agent_response))
            print(f"agent: {agent_response}")

    if test_mode:
        try:
            for line in sys.stdin:
                message = line.strip()
                if not message:
                    continue
                if message.lower() in ["quit", "exit"]:
                    break
                # Skip adding token summary messages and their responses to the ticket
                if message.lower() == "**tokens**":
                    agent_response = await chat_client.send_message(message)
                    print(f"agent: {agent_response}")
                    print(AGENT_MESSAGE_TERMINATOR)
                    continue
                add_user_article(message)
                agent_response = await chat_client.send_message(message)
                add_agent_article(str(agent_response))
                print(f"agent: {agent_response}")
                print(AGENT_MESSAGE_TERMINATOR)
                emit_status()
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
                        agent_response = await chat_client.send_message(message)
                        print(f"agent: {agent_response}")
                        continue
                    add_user_article(message)
                    agent_response = await chat_client.send_message(message)
                    add_agent_article(str(agent_response))
                    print(f"agent: {agent_response}")
                    emit_status()
            except KeyboardInterrupt:
                break

    await chat_client.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI Chat with Request Manager and Zammad ticket tracking"
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
        "--delete-ticket-on-close",
        action="store_true",
        help="Delete the Zammad ticket when the session ends",
    )
    parser.add_argument(
        "--show-ticket-status",
        action="store_true",
        help="Emit a TICKET_STATUS line after each agent response",
    )
    args = parser.parse_args()

    base_user_id = args.user_id or USER_ID or AUTHORITATIVE_USER_ID
    request_manager_url = args.request_manager_url or REQUEST_MANAGER_URL
    initial_message = (
        args.initial_message or "please introduce yourself and tell me how you can help"
    )

    zammad_base_url = ZAMMAD_URL
    zammad_token = ZAMMAD_HTTP_TOKEN

    ticket_id: int | None = None
    ticket_number: str | None = None
    state_map: dict[int, str] = {}
    agent_user_id: int | None = None

    if zammad_base_url and zammad_token and base_user_id:
        try:
            state_map = _zammad_get_state_map(zammad_base_url, zammad_token)
            agent_user_id = _zammad_get_user_id_by_email(
                zammad_base_url, zammad_token, AGENT_EMAIL
            )
            ticket_id, ticket_number = _zammad_create_ticket(
                zammad_base_url, zammad_token, base_user_id, title=args.ticket_title
            )
            print(f"Created Zammad ticket #{ticket_number} (id={ticket_id})")
        except Exception as e:
            print(f"Warning: could not create Zammad ticket: {e}", file=sys.stderr)

    # Append internal ticket id (not display number) to user_id for session uniqueness
    # The Zammad MCP server expects the internal id from /api/v1/tickets/{id}, not the display number
    if ticket_id:
        user_id = f"{base_user_id}-{ticket_id}"
    else:
        user_id = base_user_id

    chat_client = CLIChatClient(
        request_manager_url=request_manager_url,
        user_id=user_id,
    )

    if user_id:
        print(f"Using user ID: {user_id}")
    else:
        print("No user ID specified - using auto-generated UUID")

    print("Using LangGraph state machine for conversation management")

    try:
        await _chat_loop_with_status(
            chat_client,
            initial_message=initial_message,
            ticket_id=ticket_id,
            ticket_number=ticket_number,
            customer_email=base_user_id,
            agent_user_id=agent_user_id,
            zammad_base_url=zammad_base_url,
            zammad_token=zammad_token,
            state_map=state_map,
            show_ticket_status=args.show_ticket_status,
            test_mode=not sys.stdin.isatty(),
        )
    finally:
        if (
            args.delete_ticket_on_close
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
