def parse_email_and_ticket_id(authoritative_user_id: str) -> tuple[str, int]:
    """Return (email lowercased, internal ticket id). Format: local@domain-123 (id is numeric)."""
    if not authoritative_user_id or not str(authoritative_user_id).strip():
        raise ValueError("AUTHORITATIVE_USER_ID is empty.")

    raw = str(authoritative_user_id).strip()
    if "@" not in raw:
        raise ValueError(
            "AUTHORITATIVE_USER_ID must be {email}-{ticket_id} "
            "(email must contain '@')."
        )
    if "-" not in raw:
        raise ValueError(
            "AUTHORITATIVE_USER_ID must be {email}-{ticket_id} "
            "(missing '-' before ticket id)."
        )

    left, ticket_str = raw.rsplit("-", 1)
    ticket_str = ticket_str.strip()
    if not ticket_str.isdigit():
        raise ValueError(
            "AUTHORITATIVE_USER_ID must end with a numeric Zammad ticket id, "
            f"e.g. user@example.com-99; got suffix {ticket_str!r}."
        )

    email = left.strip().lower()
    if "@" not in email:
        raise ValueError("AUTHORITATIVE_USER_ID email portion is invalid.")

    return email, int(ticket_str)
