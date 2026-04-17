"""Tests for AUTHORITATIVE_USER_ID parsing."""

import pytest
from zammad_mcp.zammad_auth_id import parse_email_and_ticket_id


def test_parse_ok() -> None:
    assert parse_email_and_ticket_id("alice@company.com-42") == (
        "alice@company.com",
        42,
    )


def test_parse_strips_and_lowercases_email() -> None:
    assert parse_email_and_ticket_id("  Alice@Company.COM-7  ") == (
        "alice@company.com",
        7,
    )


def test_parse_email_with_hyphen_local_part() -> None:
    assert parse_email_and_ticket_id("a-b@co.com-99") == ("a-b@co.com", 99)


def test_parse_rejects_non_numeric_suffix() -> None:
    with pytest.raises(ValueError, match="numeric"):
        parse_email_and_ticket_id("alice@company.com-abc")


def test_parse_rejects_no_at() -> None:
    with pytest.raises(ValueError, match="@"):
        parse_email_and_ticket_id("not-an-email-1")


def test_parse_rejects_missing_hyphen() -> None:
    with pytest.raises(ValueError, match="missing"):
        parse_email_and_ticket_id("alice@company.com")
