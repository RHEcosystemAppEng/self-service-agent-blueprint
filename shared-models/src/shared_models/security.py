"""Security utilities for shared authentication and verification."""

import hashlib
import hmac
import time

import structlog

logger = structlog.get_logger()


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    debug_logging: bool = False,
) -> bool:
    """
    Verify Slack request signature using HMAC-SHA256.

    Args:
        body: Raw request body bytes
        timestamp: Slack timestamp header
        signature: Slack signature header
        secret: Slack signing secret
        debug_logging: Whether to enable debug logging

    Returns:
        True if signature is valid, False otherwise
    """
    if debug_logging:
        logger.debug(
            "Slack signature verification called",
            timestamp=timestamp,
            signature_preview=signature[:20] + "..." if signature else "None",
        )

    if not secret:
        logger.warning("Slack signing secret not configured, skipping verification")
        return True  # Skip verification if not configured

    # Check timestamp to prevent replay attacks
    current_time = int(time.time())
    request_time = int(timestamp)

    if abs(current_time - request_time) > 300:  # 5 minutes
        if debug_logging:
            logger.warning("Slack request timestamp too old", timestamp=timestamp)
        return False

    # Create signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_signature = (
        "v0="
        + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    )

    return hmac.compare_digest(expected_signature, signature)
