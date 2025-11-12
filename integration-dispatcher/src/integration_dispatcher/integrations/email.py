"""Email integration handler."""

import os
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Callable, Dict, Optional, Union

import aiosmtplib
from shared_models import configure_logging
from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig

from .base import BaseIntegrationHandler, IntegrationResult

logger = configure_logging("integration-dispatcher")


def _validate_starttls_response(response: str) -> bool:
    """Validate that STARTTLS is supported in the server response."""
    return "STARTTLS" in response


def _test_socket_connectivity(
    host: str,
    port: int,
    use_ssl: bool = False,
    server_hostname: Optional[str] = None,
    command: Optional[bytes] = None,
    response_validator: Optional[Callable[[str], bool]] = None,
    protocol_name: str = "server",
) -> bool:
    """Test socket connectivity with optional SSL and command validation.

    Args:
        host: Server hostname
        port: Server port
        use_ssl: Whether to use SSL/TLS
        server_hostname: Hostname for SSL certificate validation
        command: Command to send after connection (e.g., b"EHLO health-check\r\n")
        response_validator: Function to validate response (returns True if valid)
        protocol_name: Name of protocol for logging (e.g., "SMTP", "IMAP")

    Returns:
        True if connectivity test passed, False otherwise
    """
    sock = None
    ssl_sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)

        # Connect to server
        sock.connect((host, port))
        logger.debug(
            "TCP connection to server established",
            protocol=protocol_name,
            host=host,
            port=port,
        )

        # Wrap with SSL if needed
        active_sock: Union[socket.socket, ssl.SSLSocket]
        if use_ssl:
            context = ssl.create_default_context()
            ssl_sock = context.wrap_socket(
                sock, server_hostname=server_hostname or host
            )
            active_sock = ssl_sock
        else:
            active_sock = sock

        # Read initial greeting
        response = active_sock.recv(1024).decode("utf-8")
        logger.debug(
            "Server greeting received",
            protocol=protocol_name,
            response=response[:100],
        )

        # Send command if provided
        if command:
            active_sock.send(command)
            response = active_sock.recv(1024).decode("utf-8")
            logger.debug("Command response received", response=response[:100])

            # Validate response if validator provided
            if response_validator:
                if not response_validator(response):
                    logger.warning("Response validation failed", protocol=protocol_name)
                    return False

        logger.debug("Connectivity test passed", protocol=protocol_name)
        return True

    except ssl.SSLError as e:
        logger.error(
            "SSL connection failed",
            protocol=protocol_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return False
    except Exception as e:
        logger.error(
            "Connection test failed",
            protocol=protocol_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return False
    finally:
        if ssl_sock:
            ssl_sock.close()
        if sock:
            sock.close()


class EmailIntegrationHandler(BaseIntegrationHandler):
    """Handler for email delivery."""

    def __init__(self) -> None:
        super().__init__()
        # SMTP configuration (sending)
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_email = os.getenv("FROM_EMAIL", "noreply@selfservice.local")
        self.from_name = os.getenv("FROM_NAME", "Self-Service Agent")

        # IMAP configuration (receiving) - reuses SMTP credentials by default
        self.imap_host = os.getenv("IMAP_HOST")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.imap_username = os.getenv("IMAP_USERNAME") or self.smtp_username
        self.imap_password = os.getenv("IMAP_PASSWORD") or self.smtp_password
        self.imap_use_ssl = os.getenv("IMAP_USE_SSL", "true").lower() == "true"
        self.imap_mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
        self.imap_poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "60"))

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """Deliver message via email."""
        try:
            email_config = config.config
            recipient_email = email_config.get("email_address")

            if not recipient_email:
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message="No email address configured",
                )

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = template_content.get("subject", "Agent Response")
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = recipient_email

            # Add reply-to if configured
            reply_to = email_config.get("reply_to")
            if reply_to:
                msg["Reply-To"] = reply_to

            # Add custom headers
            msg["X-Request-ID"] = request.request_id
            msg["X-Session-ID"] = request.session_id
            msg["X-Agent-ID"] = (
                request.agent_id if request.agent_id is not None else "system"
            )

            # Create email content
            email_format = email_config.get("format", "html")
            if email_format == "html":
                html_content = self._create_html_content(
                    template_content.get("body", ""),
                    request,
                    dict(email_config) if email_config else {},
                )
                msg.attach(MIMEText(html_content, "html"))
            else:
                text_content = self._create_text_content(
                    template_content.get("body", ""),
                    request,
                    dict(email_config) if email_config else {},
                )
                msg.attach(MIMEText(text_content, "plain"))

            # Send email
            # For port 587, we need to use STARTTLS (plain connection first, then upgrade to TLS)
            # For port 465, we use SSL/TLS from the start
            if self.smtp_port == 587 and self.smtp_use_tls:
                # Port 587 with STARTTLS
                await aiosmtplib.send(
                    msg,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.smtp_username,
                    password=self.smtp_password,
                    use_tls=False,  # Start with plain connection
                    start_tls=True,  # Then upgrade to TLS
                )
            else:
                # Port 465 or other configurations
                await aiosmtplib.send(
                    msg,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.smtp_username,
                    password=self.smtp_password,
                    use_tls=self.smtp_use_tls,
                )

            return IntegrationResult(
                success=True,
                status=DeliveryStatus.DELIVERED,
                message="Email sent successfully",
                metadata={
                    "recipient": recipient_email,
                    "subject": msg["Subject"],
                },
            )

        except aiosmtplib.SMTPException as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"SMTP error: {str(e)}",
                retry_after=300,  # Retry after 5 minutes
            )
        except Exception as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Unexpected error: {str(e)}",
            )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate email configuration."""
        email_address = config.get("email_address")
        if not email_address or "@" not in email_address:
            return False

        # Validate format if specified
        email_format = config.get("format", "html")
        if email_format not in ["html", "text"]:
            return False

        return True

    async def health_check(self) -> bool:
        """Check email integration health (SMTP sending by default)."""
        return await self.health_check_sending()

    async def health_check_sending(self) -> bool:
        """Check email sending capability (SMTP)."""
        # Return False if no SMTP configuration is provided
        if not self.smtp_username or not self.smtp_password:
            logger.debug(
                "Email integration not available - no SMTP credentials configured"
            )
            return False

        logger.debug(
            "Email integration health check started (connectivity only)",
            smtp_host=self.smtp_host,
            smtp_port=self.smtp_port,
            smtp_use_tls=self.smtp_use_tls,
            has_username=bool(self.smtp_username),
            has_password=bool(self.smtp_password),
        )

        try:
            # Test SMTP connectivity without sending emails
            # This is much less intrusive and won't hit sending limits

            # Determine SSL usage based on port
            use_ssl = self.smtp_port == 465

            # For port 587 with STARTTLS, validate that STARTTLS is available
            if self.smtp_port == 587 and self.smtp_use_tls:
                logger.debug("Testing SMTP connectivity on port 587 (STARTTLS)")
                return _test_socket_connectivity(
                    host=self.smtp_host,
                    port=int(self.smtp_port),
                    use_ssl=False,
                    command=b"EHLO health-check\r\n",
                    response_validator=_validate_starttls_response,
                    protocol_name="SMTP",
                )
            else:
                # Port 465 (SMTPS) or other configurations
                logger.debug(
                    "Testing SMTP connectivity",
                    port=self.smtp_port,
                    protocol="SMTPS" if use_ssl else "plain",
                )
                return _test_socket_connectivity(
                    host=self.smtp_host,
                    port=int(self.smtp_port),
                    use_ssl=use_ssl,
                    server_hostname=self.smtp_host,
                    command=b"EHLO health-check\r\n",
                    protocol_name="SMTP",
                )

        except Exception as e:
            logger.error(
                "Email integration health check failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def health_check_receiving(self) -> bool:
        """Check email receiving capability (IMAP).

        Similar to SMTP health check, tests IMAP connectivity without
        actually processing emails. Uses lightweight connection test.
        """
        # Return False if no IMAP configuration is provided
        if not self.imap_username or not self.imap_password:
            logger.debug("IMAP not available - no IMAP credentials configured")
            return False

        if not self.imap_host:
            logger.debug("IMAP not available - no IMAP host configured")
            return False

        logger.debug(
            "IMAP health check started (connectivity only)",
            imap_host=self.imap_host,
            imap_port=self.imap_port,
            imap_use_ssl=self.imap_use_ssl,
            has_username=bool(self.imap_username),
            has_password=bool(self.imap_password),
        )

        try:
            # Test IMAP connectivity without processing emails
            # Similar lightweight approach to SMTP health check

            if self.imap_use_ssl:
                # Port 993 (IMAPS) - SSL/TLS from the start
                logger.debug("Testing IMAP connectivity on port 993 (IMAPS)")
                return _test_socket_connectivity(
                    host=self.imap_host,
                    port=int(self.imap_port),
                    use_ssl=True,
                    server_hostname=self.imap_host,
                    command=b"a1 CAPABILITY\r\n",
                    protocol_name="IMAP",
                )
            else:
                # Port 143 (STARTTLS) - plain connection first, then upgrade
                logger.debug("Testing IMAP connectivity on port 143 (STARTTLS)")
                return _test_socket_connectivity(
                    host=self.imap_host,
                    port=int(self.imap_port),
                    use_ssl=False,
                    command=b"a1 CAPABILITY\r\n",
                    response_validator=_validate_starttls_response,
                    protocol_name="IMAP",
                )

        except Exception as e:
            logger.error(
                "IMAP health check failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def get_required_config_fields(self) -> list[str]:
        """Required email configuration fields."""
        return ["email_address"]

    def get_optional_config_fields(self) -> list[str]:
        """Optional email configuration fields."""
        return [
            "display_name",
            "format",
            "include_signature",
            "reply_to",
        ]

    def _create_html_content(
        self,
        content: str,
        request: DeliveryRequest,
        config: Dict[str, Any],
    ) -> str:
        """Create HTML email content."""
        # Convert markdown-like content to HTML
        html_content = content.replace("\n", "<br>")

        # Basic HTML template
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
                .content {{ padding: 20px; }}
                .footer {{ margin-top: 30px; padding: 15px; background-color: #f8f9fa; font-size: 0.9em; color: #666; }}
                .agent-info {{ font-style: italic; color: #666; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Self-Service Agent Response</h2>
            </div>

            <div class="content">
                {html_content}
            </div>

            {self._get_agent_info_html(request) if config.get("include_agent_info", True) else ""}

            <div class="footer">
                <p>Request ID: {request.request_id}</p>
                <p>Session ID: {request.session_id}</p>
                {self._get_signature_html() if config.get("include_signature", True) else ""}
            </div>
        </body>
        </html>
        """

        return html

    def _create_text_content(
        self,
        content: str,
        request: DeliveryRequest,
        config: Dict[str, Any],
    ) -> str:
        """Create plain text email content."""
        text_parts = [
            "Self-Service Agent Response",
            "=" * 30,
            "",
            content,
            "",
        ]

        if config.get("include_agent_info", True) and request.agent_id:
            text_parts.extend(
                [
                    f"Response from agent: {request.agent_id}",
                    "",
                ]
            )

        text_parts.extend(
            [
                "-" * 30,
                f"Request ID: {request.request_id}",
                f"Session ID: {request.session_id}",
            ]
        )

        if config.get("include_signature", True):
            text_parts.extend(
                [
                    "",
                    "This is an automated message from the Self-Service Agent system.",
                ]
            )

        return "\n".join(text_parts)

    def _get_agent_info_html(self, request: DeliveryRequest) -> str:
        """Get HTML for agent information."""
        if not request.agent_id:
            return ""

        return f'<div class="agent-info">Response from agent: {request.agent_id}</div>'

    def _get_signature_html(self) -> str:
        """Get HTML signature."""
        return "<p><em>This is an automated message from the Self-Service Agent system.</em></p>"
