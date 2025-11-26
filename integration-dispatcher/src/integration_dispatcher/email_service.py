"""Email service for handling incoming emails via IMAP."""

import asyncio
import hashlib
import os
import re
import socket
import uuid
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.utils import parseaddr
from typing import Any, Dict, Optional

import aioimaplib
from shared_models import (
    CloudEventSender,
    DatabaseUtils,
    configure_logging,
)
from shared_models.database import get_database_manager
from shared_models.models import IntegrationType, ProcessedEvent
from sqlalchemy import select, text

from .user_mapping_utils import resolve_user_id_from_email

logger = configure_logging("integration-dispatcher")


class EmailService:
    """Service for handling incoming emails via IMAP polling."""

    def __init__(self) -> None:

        # Reuse existing email credentials (same account as sending)
        self.imap_host = os.getenv("IMAP_HOST")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.imap_username = os.getenv("IMAP_USERNAME") or os.getenv("SMTP_USERNAME")
        self.imap_password = os.getenv("IMAP_PASSWORD") or os.getenv("SMTP_PASSWORD")
        self.imap_mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
        self.poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "60"))
        self.imap_use_ssl = os.getenv("IMAP_USE_SSL", "true").lower() == "true"

        # Email addresses to ignore (system email addresses)
        # Get FROM_EMAIL if configured, otherwise use SMTP_USERNAME as fallback
        self.from_email = os.getenv("FROM_EMAIL", "")
        self._ignore_addresses = set()
        if self.from_email:
            self._ignore_addresses.add(self.from_email.lower())
        if self.imap_username:
            self._ignore_addresses.add(self.imap_username.lower())

        # Eventing configuration (required - validated at startup)
        self.broker_url = os.getenv("BROKER_URL")
        if not self.broker_url:
            raise ValueError(
                "BROKER_URL is required but not configured. "
                "Email service cannot forward requests to Request Manager without it."
            )
        self.cloudevent_sender = CloudEventSender(
            self.broker_url, "integration-dispatcher"
        )

        # Leader election configuration
        self.pod_id = (
            os.getenv("HOSTNAME")
            or os.getenv("POD_NAME")
            or socket.gethostname()
            or str(uuid.uuid4())
        )
        self.lease_duration = int(
            os.getenv("IMAP_LEASE_DURATION", "120")
        )  # Lease duration in seconds (should be 2x poll_interval for safety margin)
        # Lease renewal interval (how often to renew the lease)
        # Default: half of lease_duration, but can be configured separately
        renewal_interval_env = os.getenv("IMAP_LEASE_RENEWAL_INTERVAL")
        if renewal_interval_env:
            self.lease_renewal_interval = int(renewal_interval_env)
        else:
            self.lease_renewal_interval = self.lease_duration // 2
        self._is_leader = False
        self._leader_lease_expiry: Optional[datetime] = None
        self._lock_connection: Optional[Any] = (
            None  # Keep database session open to hold advisory lock
        )
        self._lock_context_manager: Optional[Any] = (
            None  # Track the context manager for proper cleanup
        )

        # Compute lock key once (must be in 32-bit unsigned range for PostgreSQL)
        # Use consistent hash (MD5) to ensure same value across pod restarts
        # Take first 32 bits (4 bytes) to fit in 32-bit unsigned range (0 to 2^32-1)
        # PostgreSQL advisory locks use BIGINT, but to avoid "OID out of range" errors,
        # we constrain the value to 32-bit unsigned range
        lock_key_bytes = hashlib.md5("imap_leader_election".encode()).digest()[:4]
        self._lock_key = int.from_bytes(
            lock_key_bytes, byteorder="big"
        )  # 32-bit unsigned value

        # Simple rate limiting: track last request time per user
        self._last_request_time: Dict[str, float] = {}

    def _create_email_message_id(
        self, message_id: Optional[str], from_addr: str, date: Optional[str]
    ) -> str:
        """Create a unique identifier for an email message."""
        if message_id:
            # Use Message-ID header which is globally unique
            return f"email-{message_id}"
        else:
            # Fallback to from address and date if Message-ID missing
            date_str = date or "unknown"
            return f"email-{from_addr}-{date_str}"

    def _normalize_email_id(self, email_id: Any) -> bytes:
        """Normalize email ID to bytes format expected by IMAP operations.

        Handles cases where email_id might be bytes, str, or int.
        """
        if isinstance(email_id, bytes):
            return email_id
        elif isinstance(email_id, str):
            return email_id.encode("utf-8")
        elif isinstance(email_id, int):
            return str(email_id).encode("utf-8")
        else:
            return str(email_id).encode("utf-8")

    def _email_id_to_str(self, email_id: Any) -> str:
        """Convert email ID to string for logging purposes."""
        if isinstance(email_id, bytes):
            return email_id.decode("utf-8")
        elif isinstance(email_id, (str, int)):
            return str(email_id)
        else:
            return str(email_id)

    async def start_polling(self) -> None:
        """Start IMAP polling in background task using leader election.

        Only the leader pod polls IMAP; other pods wait and periodically
        check if they can become leader. If leader dies, another pod takes over.
        """
        if not self.imap_host or not self.imap_username or not self.imap_password:
            logger.warning(
                "IMAP polling not started - missing configuration",
                has_host=bool(self.imap_host),
                has_username=bool(self.imap_username),
                has_password=bool(self.imap_password),
            )
            return

        logger.info(
            "Starting IMAP email polling with leader election",
            imap_host=self.imap_host,
            imap_port=self.imap_port,
            mailbox=self.imap_mailbox,
            poll_interval=self.poll_interval,
            pod_id=self.pod_id,
            lease_duration=self.lease_duration,
            lease_renewal_interval=self.lease_renewal_interval,
        )

        # Leader election loop: try to become leader and maintain lease
        while True:
            try:
                is_leader = await self._try_become_leader()

                if is_leader:
                    # We are the leader - poll mailbox and renew lease
                    logger.info(
                        "Elected as leader - starting IMAP polling",
                        pod_id=self.pod_id,
                    )
                    self._is_leader = True

                    # Track last poll time to respect poll_interval
                    last_poll_time = None
                    last_lease_renewal_time = None

                    while self._is_leader:
                        try:
                            now = datetime.now(timezone.utc)

                            # Renew lease if needed (every lease_renewal_interval)
                            if (
                                last_lease_renewal_time is None
                                or (now - last_lease_renewal_time).total_seconds()
                                >= self.lease_renewal_interval
                            ):
                                if not await self._renew_lease():
                                    logger.warning(
                                        "Failed to renew lease - losing leadership",
                                        pod_id=self.pod_id,
                                    )
                                    # _renew_lease() already calls _release_leadership() internally
                                    # which sets self._is_leader = False, so the loop will exit
                                    break
                                last_lease_renewal_time = now

                            # Poll mailbox if poll_interval has elapsed
                            if (
                                last_poll_time is None
                                or (now - last_poll_time).total_seconds()
                                >= self.poll_interval
                            ):
                                await self._poll_mailbox()
                                last_poll_time = now

                            # Sleep until next polling cycle or lease renewal
                            # Wake up at the earlier of: next poll time or next lease renewal time
                            time_until_next_poll = (
                                self.poll_interval
                                - (now - last_poll_time).total_seconds()
                                if last_poll_time
                                else self.poll_interval
                            )
                            time_until_next_renewal = (
                                self.lease_renewal_interval
                                - (now - last_lease_renewal_time).total_seconds()
                                if last_lease_renewal_time
                                else self.lease_renewal_interval
                            )
                            sleep_time = min(
                                time_until_next_poll, time_until_next_renewal
                            )
                            # Ensure we sleep at least 1 second to avoid busy loop
                            sleep_time = max(1.0, sleep_time)
                            await asyncio.sleep(sleep_time)
                        except Exception as e:
                            logger.error(
                                "Error during leader polling",
                                error=str(e),
                                error_type=type(e).__name__,
                                pod_id=self.pod_id,
                                exc_info=True,
                            )
                            # If we lose leadership due to error, release and retry
                            await self._release_leadership()
                            await asyncio.sleep(5)  # Brief pause before retrying
                            break
                else:
                    # Not the leader - wait and periodically check for leadership
                    logger.debug(
                        "Not leader - waiting to check for leadership",
                        pod_id=self.pod_id,
                        current_leader=await self._get_current_leader(),
                    )
                    # Check for leadership opportunity every 1/3 of lease duration
                    await asyncio.sleep(self.lease_renewal_interval)
            except Exception as e:
                logger.error(
                    "Leader election error",
                    error=str(e),
                    pod_id=self.pod_id,
                )
                await asyncio.sleep(self.lease_renewal_interval)

    async def _try_become_leader(self) -> bool:
        """Try to become the leader pod for IMAP polling.

        Uses PostgreSQL advisory lock to ensure only one leader exists.
        The lock is held by keeping a database session open.

        Returns:
            True if this pod became/remains leader, False otherwise
        """
        # If we already have a lock session, verify it's still alive and we hold the lock
        if self._lock_connection is not None:
            try:
                result = await self._lock_connection.execute(
                    text("SELECT pg_advisory_lock_held(:key)"),
                    {"key": self._lock_key},
                )
                still_has_lock = result.scalar()
                if still_has_lock:
                    return True
                else:
                    # Lock not held, release leadership
                    await self._release_leadership()
                    return False
            except Exception:
                # Session is dead, release leadership
                await self._release_leadership()
                return False

        db_manager = get_database_manager()

        # Create a new context manager and enter it manually
        # We need to keep the session alive to hold the lock
        lock_context = db_manager.get_session()
        lock_db = None
        try:
            # Manually enter the context manager
            # We'll exit it manually in _release_leadership
            lock_db = await lock_context.__aenter__()

            # Try to acquire advisory lock (non-blocking)
            # No commit needed - advisory locks are session-level
            result = await lock_db.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": self._lock_key},
            )
            has_lock = result.scalar()

            if has_lock:
                # We got the lock - become leader
                # Keep the session open to hold the lock
                self._lock_connection = lock_db
                self._lock_context_manager = lock_context
                now = datetime.now(timezone.utc)
                lease_expiry = now + timedelta(seconds=self.lease_duration)
                self._leader_lease_expiry = lease_expiry

                logger.info(
                    "Became leader",
                    pod_id=self.pod_id,
                    lease_expiry=lease_expiry.isoformat(),
                )
                return True
            else:
                # Lock held by another pod - not leader
                # Exit the context manager properly
                await lock_context.__aexit__(None, None, None)
                self._is_leader = False
                self._leader_lease_expiry = None
                return False

        except Exception as e:
            logger.error(
                "Error during leader election",
                error=str(e),
                pod_id=self.pod_id,
            )
            if lock_context and lock_db:
                try:
                    await lock_context.__aexit__(type(e), e, None)
                except Exception:
                    pass
            return False

    async def _renew_lease(self) -> bool:
        """Renew the leader lease if we are still the leader.

        Uses pg_advisory_lock_held to check if we still hold the lock.

        Returns:
            True if lease renewed successfully, False if we lost leadership
        """
        if self._lock_connection is None:
            # No lock session means we're not leader
            self._is_leader = False
            self._leader_lease_expiry = None
            return False

        try:
            # Check if we still hold the lock using the custom function
            result = await self._lock_connection.execute(
                text("SELECT pg_advisory_lock_held(:key)"),
                {"key": self._lock_key},
            )
            still_has_lock = result.scalar()

            if still_has_lock:
                # Still leader - renew lease
                now = datetime.now(timezone.utc)
                lease_expiry = now + timedelta(seconds=self.lease_duration)
                self._leader_lease_expiry = lease_expiry
                return True
            else:
                # Lost leadership
                logger.warning(
                    "Lost leadership - lock no longer held",
                    pod_id=self.pod_id,
                )
                await self._release_leadership()
                return False

        except Exception as e:
            # Session error means we lost leadership
            logger.error(
                "Error renewing lease - session lost",
                error=str(e),
                pod_id=self.pod_id,
            )
            await self._release_leadership()
            return False

    async def _release_leadership(self) -> None:
        """Release leadership and close the lock session."""
        lock_context = self._lock_context_manager
        self._lock_connection = None
        self._lock_context_manager = None
        self._is_leader = False
        self._leader_lease_expiry = None

        if lock_context:
            try:
                # Exit the context manager properly
                # This will close the session and release the advisory lock
                await lock_context.__aexit__(None, None, None)
            except Exception:
                pass  # Ignore errors during cleanup

    async def _get_current_leader(self) -> Optional[str]:
        """Get the current leader pod ID (for logging/debugging).

        Returns:
            Pod ID of current leader, or None if no leader
        """
        # In simple implementation, we don't track who is leader in a table
        # We just know if we hold the lock or not
        if self._is_leader and self._leader_lease_expiry:
            if datetime.now(timezone.utc) < self._leader_lease_expiry:
                return self.pod_id
        return None

    async def _poll_mailbox(self) -> None:
        """Poll IMAP mailbox for new emails.

        This is only called by the leader pod. No locks needed since
        only one pod polls at a time via leader election.
        """
        imap_client = None
        try:
            # Create IMAP client based on SSL configuration
            if self.imap_use_ssl:
                imap_client = aioimaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                imap_client = aioimaplib.IMAP4(self.imap_host, self.imap_port)

            # Wait for server greeting before sending commands
            await imap_client.wait_hello_from_server()

            await imap_client.login(self.imap_username, self.imap_password)

            # Select mailbox and verify success
            select_typ, select_data = await imap_client.select(self.imap_mailbox)
            if select_typ != "OK":
                logger.error(
                    "IMAP SELECT failed",
                    status=select_typ,
                    mailbox=self.imap_mailbox,
                    response=str(select_data) if select_data else None,
                )
                return  # Can't proceed without mailbox selection

            # Search for unread emails
            # For flag-based searches like UNSEEN, charset parameter shouldn't be included
            # aioimaplib's search() method includes charset if charset is not None
            # Pass charset=None explicitly to omit charset parameter for flag searches
            try:
                # Pass charset=None to omit charset parameter (aioimaplib only includes it if charset is not None)
                typ, data = await imap_client.search("UNSEEN", charset=None)
            except Exception as e:
                logger.error(
                    "Failed to send IMAP search command",
                    error=str(e),
                    mailbox=self.imap_mailbox,
                )
                raise
            email_ids_to_process = []

            # Check if search was successful
            if typ != "OK":
                logger.error(
                    "IMAP search failed",
                    status=typ,
                    mailbox=self.imap_mailbox,
                    response=str(data) if data else None,
                )
            elif data and data[0]:
                # Normalize email IDs and validate they are numeric
                if isinstance(data[0], bytes):
                    email_ids_str = data[0].decode("utf-8")
                else:
                    email_ids_str = str(data[0])

                # Split and filter to only valid numeric email IDs
                email_ids = []
                for email_id in email_ids_str.split():
                    # Validate that it's a numeric email ID
                    try:
                        int(email_id)  # Validate it's a number
                        email_ids.append(email_id)
                    except ValueError:
                        logger.warning(
                            "Invalid email ID from IMAP search - skipping",
                            email_id=email_id,
                            mailbox=self.imap_mailbox,
                        )
                        continue

                if email_ids:
                    logger.debug(
                        "Found unread emails",
                        count=len(email_ids),
                        mailbox=self.imap_mailbox,
                    )
                    # With leader election, only this pod polls, so no need to mark as read immediately
                    # We'll mark as read after successful processing to allow retries on failure
                    email_ids_to_process = email_ids
                else:
                    logger.debug("No unread emails found", mailbox=self.imap_mailbox)
            else:
                logger.debug("No unread emails found", mailbox=self.imap_mailbox)

            # Process emails (mark as read only after successful processing)
            for email_id in email_ids_to_process:
                success = await self._process_email(email_id, imap_client)
                if success:
                    # Mark as read only after successful processing
                    # This allows retries if processing fails
                    try:
                        await imap_client.store(email_id, "+FLAGS", "\\Seen")
                        logger.debug(
                            "Email processed and marked as read",
                            email_id=email_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to mark email as read after processing",
                            email_id=email_id,
                            error=str(e),
                        )
                        # Processing succeeded, so continue even if mark failed
                else:
                    logger.debug(
                        "Email processing failed - leaving unread for retry",
                        email_id=email_id,
                    )

            await imap_client.logout()

        except Exception as e:
            logger.error(
                "Error polling IMAP mailbox",
                error=str(e) if str(e) else repr(e),
                error_type=type(e).__name__,
                mailbox=self.imap_mailbox,
                exc_info=True,
            )
            # Ensure connection is closed on error
            if imap_client:
                try:
                    await imap_client.logout()
                except Exception:
                    pass  # Ignore errors during cleanup
            raise

    async def _process_email(self, email_id: str, imap_client: Any) -> bool:
        """Process a single email."""
        db_manager = get_database_manager()
        async with db_manager.get_session() as db:
            try:
                # Fetch email - aioimaplib expects string email IDs
                typ, data = await imap_client.fetch(email_id, "(RFC822)")
                if not data or not data[0]:
                    logger.warning(
                        "Failed to fetch email",
                        email_id=email_id,
                    )
                    return False

                # Extract email body from fetch response
                # aioimaplib returns email in chunks (bytes or bytearray) that may include IMAP status lines
                # We need to find where the email headers start and extract from there

                # Flatten all chunks into a list, converting bytearray to bytes
                all_chunks = []
                for item in data:
                    if isinstance(item, (bytes, bytearray)):
                        all_chunks.append(
                            bytes(item) if isinstance(item, bytearray) else item
                        )
                    elif isinstance(item, (tuple, list)):
                        for part in item:
                            if isinstance(part, (bytes, bytearray)):
                                all_chunks.append(
                                    bytes(part) if isinstance(part, bytearray) else part
                                )

                if not all_chunks:
                    logger.error(
                        "No bytes found in fetch response",
                        email_id=email_id,
                        data_type=type(data).__name__,
                        data_len=len(data) if hasattr(data, "__len__") else None,
                    )
                    return False

                # Search for first email header marker to strip IMAP status line prefix
                header_markers = [
                    b"Delivered-To:",
                    b"Received:",
                    b"Return-Path:",
                    b"From:",
                    b"Message-ID:",
                ]

                concatenated_chunks = b"".join(all_chunks)
                email_start_chunk_idx = None
                email_start_pos = None

                for marker in header_markers:
                    marker_pos = concatenated_chunks.find(marker)
                    if marker_pos >= 0:
                        # Found the marker - figure out which chunk it's in
                        current_pos = 0
                        for chunk_idx, chunk in enumerate(all_chunks):
                            chunk_end = current_pos + len(chunk)
                            if current_pos <= marker_pos < chunk_end:
                                email_start_chunk_idx = chunk_idx
                                email_start_pos = marker_pos - current_pos
                                break
                            current_pos = chunk_end
                        break

                if email_start_chunk_idx is not None:
                    # Extract from the marker onwards
                    email_body_parts = []
                    email_body_parts.append(
                        all_chunks[email_start_chunk_idx][email_start_pos:]
                    )
                    for chunk in all_chunks[email_start_chunk_idx + 1 :]:
                        email_body_parts.append(chunk)
                    email_body = b"".join(email_body_parts)
                else:
                    # No marker found - use all chunks (fallback for different IMAP server formats)
                    email_body = concatenated_chunks

                if not email_body or len(email_body) == 0:
                    logger.error(
                        "Email body is empty",
                        email_id=email_id,
                    )
                    return False

                # Parse email message from bytes
                try:
                    email_message = message_from_bytes(email_body)
                except Exception as e:
                    logger.error(
                        "Failed to parse email message from bytes",
                        email_id=email_id,
                        error=str(e),
                    )
                    return False

                # Extract email data
                from_header = email_message.get("From", "")

                parsed_from = parseaddr(from_header) if from_header else ("", "")
                from_addr = parsed_from[1] if parsed_from else ""

                # If parseaddr didn't extract an email, try to extract from the header directly
                if not from_addr and from_header:
                    # Try to extract email address using regex as fallback
                    email_pattern = (
                        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                    )
                    matches = re.findall(email_pattern, from_header)
                    if matches:
                        from_addr = matches[0]
                    else:
                        logger.warning(
                            "Could not extract email address from From header",
                            email_id=email_id,
                            from_header=from_header,
                            parsed_from=parsed_from,
                        )

                subject = email_message.get("Subject", "")
                message_id = email_message.get("Message-ID")
                date = email_message.get("Date")
                in_reply_to = email_message.get("In-Reply-To")
                references = email_message.get("References")
                # Extract X-Session-ID header if present (from previous email response)
                # Try case-insensitive lookup (email headers are case-insensitive)
                session_id = (
                    email_message.get("X-Session-ID")
                    or email_message.get("x-session-id")
                    or email_message.get("X-SESSION-ID")
                )
                # Also check all headers for debugging
                all_headers = dict(email_message.items())
                if not session_id:
                    # Log available headers for debugging
                    logger.debug(
                        "X-Session-ID header not found in email",
                        email_id=email_id,
                        from_addr=from_addr,
                        available_headers=list(all_headers.keys()),
                        has_in_reply_to=bool(in_reply_to),
                        has_references=bool(references),
                    )
                else:
                    logger.info(
                        "Found X-Session-ID header in email reply",
                        email_id=email_id,
                        from_addr=from_addr,
                        session_id=session_id,
                    )

                if not from_addr:
                    logger.warning(
                        "Email missing From address",
                        email_id=email_id,
                        from_header=from_header,
                    )
                    return False

                # Ignore emails from system email addresses (FROM_EMAIL, SMTP_USERNAME)
                # This prevents processing emails sent by the system itself, auto-replies,
                # bounces, and other system-generated messages
                from_addr_lower = from_addr.lower()
                if from_addr_lower in self._ignore_addresses:
                    logger.debug(
                        "Ignoring email from system address",
                        email_id=email_id,
                        from_addr=from_addr,
                        system_addresses=list(self._ignore_addresses),
                    )
                    # Mark as read to avoid reprocessing
                    try:
                        await imap_client.store(email_id, "+FLAGS", "\\Seen")
                    except Exception:
                        pass  # Ignore errors when marking as read
                    return False

                # Create unique identifier for deduplication
                email_message_id = self._create_email_message_id(
                    message_id, from_addr, date
                )

                # ✅ ATOMIC EVENT CLAIMING: Use check-and-set pattern to prevent duplicate processing
                # This provides 100% guarantee - only one pod can claim and process an event
                event_claimed = await DatabaseUtils.try_claim_event_for_processing(
                    db,
                    email_message_id,
                    "email_message",
                    "imap",
                    "integration-dispatcher",
                )

                if not event_claimed:
                    logger.debug(
                        "Email already claimed by another pod - skipping duplicate",
                        email_message_id=email_message_id,
                        from_addr=from_addr,
                    )
                    # Mark as read since it's already been processed
                    try:
                        await imap_client.store(email_id, "+FLAGS", "\\Seen")
                    except Exception:
                        pass  # Ignore errors when marking as read
                    return False

                # Get body content
                body = self._extract_body(email_message)

                if not body or not body.strip():
                    logger.debug(
                        "Email has no body content - skipping",
                        from_addr=from_addr,
                        subject=subject,
                    )
                    return False

                # Resolve user_id
                user_id = await self._resolve_user_id(from_addr, db)

                # Simple rate limiting to prevent rapid-fire requests
                import time

                current_time = time.time()
                last_request_time = self._last_request_time.get(user_id, 0)

                if current_time - last_request_time < 2.0:  # 2 second cooldown
                    logger.debug(
                        "Rate limiting: ignoring rapid email request",
                        user_id=user_id,
                        time_since_last=current_time - last_request_time,
                    )
                    return False

                self._last_request_time[user_id] = current_time

                logger.info(
                    "Processing incoming email",
                    user_id=user_id,
                    from_addr=from_addr,
                    subject=subject[:50],
                    message_id=message_id,
                )

                # Forward to Request Manager
                success = await self._forward_to_request_manager(
                    user_id=user_id,
                    content=body,
                    subject=subject,
                    from_address=from_addr,
                    message_id=message_id,
                    in_reply_to=in_reply_to,
                    references=references,
                    session_id=session_id,
                )

                return success

            except Exception as e:
                logger.error(
                    "Error processing email",
                    error=str(e),
                    email_id=email_id if email_id else None,
                )
                return False

        return False  # Return False if email had no body or other early return

    async def _is_duplicate(self, email_message_id: str, db: Any) -> bool:
        """Check if email was already processed."""
        try:
            existing_event = await db.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id == email_message_id
                )
            )
            return existing_event.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(
                "Error checking for duplicate email",
                email_message_id=email_message_id,
                error=str(e),
            )
            return False

    async def _resolve_user_id(self, email_address: str, db: Any) -> str:
        """Resolve email address to canonical user_id and create mapping if needed."""
        try:
            # Use shared helper function to resolve canonical user_id with consistent logic
            # For EMAIL integration, integration_user_id is the email_address itself
            return await resolve_user_id_from_email(
                email_address=email_address,
                integration_type=IntegrationType.EMAIL,
                db=db,
                integration_specific_id=email_address,
                created_by="email_service",
            )

        except Exception as e:
            logger.error(
                "Error resolving canonical user_id from email",
                email_address=email_address,
                error=str(e),
            )
            # Re-raise the exception rather than falling back to email address
            # The email address is not a valid UUID and will cause database errors
            # If resolution fails, we should fail the request rather than proceed with invalid data
            raise

    def _extract_body(self, email_message: Any) -> str:
        """Extract text body from email message."""
        body = ""

        if email_message.is_multipart():
            # Prefer plain text, fall back to HTML
            plain_text = None
            html_text = None

            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and not plain_text:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            plain_text = payload.decode(charset, errors="replace")
                    except Exception as e:
                        logger.debug("Error decoding plain text", error=str(e))

                elif content_type == "text/html" and not html_text:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            html_text = payload.decode(charset, errors="replace")
                    except Exception as e:
                        logger.debug("Error decoding HTML", error=str(e))

            # Prefer plain text over HTML
            body = plain_text or html_text or ""

            # If HTML, strip tags (basic approach)
            if html_text and not plain_text:
                # Simple HTML tag removal
                import re

                body = re.sub(r"<[^>]+>", "", body)
                body = body.replace("&nbsp;", " ")
                body = body.replace("&amp;", "&")
                body = body.replace("&lt;", "<")
                body = body.replace("&gt;", ">")
        else:
            # Simple single-part message
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    charset = email_message.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
            except Exception as e:
                logger.debug("Error decoding message body", error=str(e))

        return body.strip()

    async def _send_cloudevent(self, event_data: Dict[str, Any]) -> bool:
        """Send a CloudEvent to the broker."""
        return await self.cloudevent_sender.send_request_event(
            request_data=event_data,
            request_id=event_data.get("request_id"),
            user_id=event_data.get("user_id"),
            session_id=event_data.get("session_id"),
        )

    async def _forward_to_request_manager(
        self,
        user_id: str,
        content: str,
        subject: str,
        from_address: str,
        message_id: Optional[str],
        in_reply_to: Optional[str],
        references: Optional[str],
        session_id: Optional[str] = None,
    ) -> bool:
        """Forward email to Request Manager via CloudEvent."""
        try:
            # Create event data - Request Manager will generate request_id and session_id
            # If session_id is provided (from X-Session-ID header), include it so Request Manager can reuse the session
            metadata = {
                "email_from": from_address,
                "email_subject": subject,
                "email_message_id": message_id,
                "email_in_reply_to": in_reply_to,
                "email_references": references,
                "source": "email_message",
            }

            event_data = {
                "user_id": user_id,
                "content": content,
                "integration_type": "EMAIL",
                "request_type": "email_interaction",
                "email_from": from_address,
                "email_subject": subject,
                "email_message_id": message_id,
                "email_in_reply_to": in_reply_to,
                "email_references": references,
                "metadata": metadata,
            }

            # Include session_id if provided (from X-Session-ID header in email reply)
            if session_id:
                event_data["session_id"] = session_id
                logger.debug(
                    "Including session_id from X-Session-ID header",
                    session_id=session_id,
                    from_address=from_address,
                )

            logger.debug(
                "Sending email request via CloudEvent to Request Manager",
                user_id=user_id,
                from_address=from_address,
                subject=subject[:50],
            )

            # Send via CloudEvent
            success = await self._send_cloudevent(event_data)
            if success:
                logger.info(
                    "Email forwarded to Request Manager via CloudEvent",
                    user_id=user_id,
                    status="success",
                )
                # Mark email as processed (read) after successful forwarding
                # This prevents reprocessing on next poll
                # Note: We still rely on deduplication as primary protection
                return True
            else:
                logger.error(
                    "Failed to forward email to Request Manager via CloudEvent",
                    user_id=user_id,
                )
                return False

        except Exception as e:
            logger.error(
                "Failed to forward email to Request Manager via CloudEvent",
                error=str(e),
                user_id=user_id,
            )
            return False
