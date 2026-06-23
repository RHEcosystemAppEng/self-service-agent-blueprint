"""Playwright e2e: laptop-refresh conversation through Zammad UI with metadata validation."""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

OWNER_ID_TO_DISPLAY: dict[str, str] = {
    "agent.laptop-specialist": "laptop",
    "manager1": "manager",
}


def _load_conversation() -> list[dict[str, Any]]:
    flow_file = (
        Path(__file__).resolve().parent.parent / "conversations" / "success-flow-1.json"
    )
    with open(flow_file) as f:
        data = json.load(f)
    return [msg for msg in data["conversation"] if msg["role"] == "user"]


def _sign_in(page: Page, zammad_url: str, email: str, password: str) -> None:
    page.goto(f"{zammad_url}/#login")
    page.wait_for_load_state("networkidle")

    page.locator("#login input[name='username']").fill(email)
    page.locator("#login input[name='password']").fill(password)
    page.locator("#login .btn--primary").click()

    page.wait_for_url(lambda url: "#login" not in url, timeout=15_000)
    page.wait_for_load_state("networkidle")


def _article_count(page: Page) -> int:
    return page.locator(".ticket-article-item").count()


def _wait_for_agent_reply(page: Page, count_before: int, timeout_s: int) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        page.reload()
        page.wait_for_load_state("networkidle")
        if _article_count(page) > count_before:
            time.sleep(2)
            return
        time.sleep(3)
    raise TimeoutError(
        f"No agent reply after {timeout_s}s "
        f"(articles: before={count_before}, now={_article_count(page)})"
    )


def _scrape_state(page: Page) -> str:
    el = page.locator(".sidebar-content select[name='state_id'] option:checked")
    if el.count() > 0:
        return el.first.inner_text().strip()
    return ""


def _scrape_owner(page: Page) -> str:
    el = page.locator(".sidebar-content select[name='owner_id'] option:checked")
    if el.count() > 0:
        return el.first.inner_text().strip()
    return ""


def _scrape_group(page: Page) -> str:
    return page.evaluate("""
        () => {
            const el = document.querySelector('[data-attribute-name="group_id"] .js-input');
            return el ? (el.value || el.textContent || '') : '';
        }
    """).strip()


def _assert_metadata(step: int, page: Page, expected: dict[str, Any]) -> None:
    state = _scrape_state(page)
    owner = _scrape_owner(page)
    group = _scrape_group(page)

    print(
        f"  Step {step + 1} metadata: state={state!r}, owner={owner!r}, group={group!r}"
    )

    if "state" in expected:
        assert expected["state"].lower() in state.lower(), (
            f"Step {step + 1}: expected state to contain "
            f"{expected['state']!r}, got {state!r}"
        )

    if "owner" in expected:
        display_name = OWNER_ID_TO_DISPLAY.get(expected["owner"], expected["owner"])
        assert display_name.lower() in owner.lower(), (
            f"Step {step + 1}: expected owner to contain "
            f"{display_name!r} (from ID {expected['owner']!r}), got {owner!r}"
        )

    if "group" in expected:
        assert expected["group"].lower() in group.lower(), (
            f"Step {step + 1}: expected group to contain "
            f"{expected['group']!r}, got {group!r}"
        )


@pytest.fixture(scope="module")
def zammad_url() -> str:
    url = os.environ.get("ZAMMAD_URL", "").rstrip("/")
    if not url:
        pytest.skip("ZAMMAD_URL not set")
    return url


@pytest.fixture(scope="module")
def reply_timeout() -> int:
    return int(os.environ.get("AGENT_REPLY_TIMEOUT", "180"))


@pytest.fixture(scope="module")
def customer_page(browser: Browser, zammad_url: str) -> Page:
    ctx = browser.new_context()
    page = ctx.new_page()
    email = os.environ.get("TEST_USER_EMAIL", "alice.johnson@company.com")
    password = os.environ.get("TEST_USER_PASSWORD", "ChangeMe123!")
    _sign_in(page, zammad_url, email, password)
    yield page
    ctx.close()


@pytest.fixture(scope="module")
def admin_page(browser: Browser, zammad_url: str) -> Page:
    ctx = browser.new_context()
    page = ctx.new_page()
    email = os.environ.get("ZAMMAD_ADMIN_EMAIL", "admin@zammad.local")
    password = os.environ.get("ZAMMAD_ADMIN_PASSWORD", "ZammadR0cks!")
    _sign_in(page, zammad_url, email, password)
    yield page
    ctx.close()


def test_laptop_refresh_conversation(
    zammad_url: str,
    reply_timeout: int,
    customer_page: Page,
    admin_page: Page,
) -> None:
    turns = _load_conversation()
    assert len(turns) >= 4, f"Expected >= 4 turns in flow, got {len(turns)}"

    customer_page.goto(f"{zammad_url}/#customer_ticket_new")
    customer_page.wait_for_load_state("networkidle")

    customer_page.locator("input[name='title']").fill("Laptop refresh help request")

    body = customer_page.locator(".richtext-content[contenteditable='true']")
    expect(body).to_be_visible(timeout=10_000)
    body.click()
    body.fill(turns[0]["content"])

    customer_page.get_by_role("button", name="Create").click()

    customer_page.wait_for_url(lambda url: "#ticket/zoom/" in url, timeout=30_000)
    customer_page.wait_for_load_state("networkidle")

    ticket_id = customer_page.url.split("/")[-1]
    print(f"Ticket created (id={ticket_id})")

    time.sleep(5)
    count = _article_count(customer_page)
    print(f"Step 1: articles after creation={count}, waiting for agent reply...")
    _wait_for_agent_reply(customer_page, count, reply_timeout)

    admin_page.goto(f"{zammad_url}/#ticket/zoom/{ticket_id}")
    admin_page.wait_for_load_state("networkidle")
    time.sleep(5)

    _assert_metadata(0, admin_page, turns[0]["expected_conversation_metadata"])

    for idx in range(1, len(turns)):
        msg = turns[idx]["content"]

        reply_box = customer_page.locator(
            ".article-new .richtext-content[contenteditable='true']"
        )
        expect(reply_box).to_be_visible(timeout=10_000)
        reply_box.click(force=True)
        reply_box.fill(msg)

        customer_page.get_by_role("button", name="Update").click()
        time.sleep(5)
        count = _article_count(customer_page)

        print(
            f"Step {idx + 1}: sent {msg!r}, articles={count}, waiting for agent reply..."
        )
        _wait_for_agent_reply(customer_page, count, reply_timeout)

        admin_page.reload()
        admin_page.wait_for_load_state("networkidle")
        time.sleep(5)
        _assert_metadata(idx, admin_page, turns[idx]["expected_conversation_metadata"])
