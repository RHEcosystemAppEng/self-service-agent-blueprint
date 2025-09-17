"""Webhook integration handler."""

from typing import Any, Dict

import httpx
from shared_db.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig

from .base import BaseIntegrationHandler, IntegrationResult


class WebhookIntegrationHandler(BaseIntegrationHandler):
    """Handler for webhook delivery."""

    def __init__(self):
        super().__init__()

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        """Deliver message via webhook."""
        try:
            webhook_config = config.config
            url = webhook_config.get("url")

            if not url:
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message="No webhook URL configured",
                )

            # Prepare payload
            payload = {
                "request_id": request.request_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "subject": template_content.get("subject"),
                "content": template_content.get("body"),
                "template_variables": request.template_variables,
                "timestamp": request.request_id,  # Could extract timestamp
            }

            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "SelfServiceAgent-IntegrationDispatcher/1.0",
                "X-Request-ID": request.request_id,
                "X-Session-ID": request.session_id,
            }

            # Add custom headers
            custom_headers = webhook_config.get("headers", {})
            headers.update(custom_headers)

            # Prepare authentication
            auth = None
            auth_type = webhook_config.get("auth_type")
            auth_config = webhook_config.get("auth_config", {})

            if auth_type == "bearer":
                token = auth_config.get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "api_key":
                api_key = auth_config.get("api_key")
                key_header = auth_config.get("key_header", "X-API-Key")
                if api_key:
                    headers[key_header] = api_key
            elif auth_type == "basic":
                username = auth_config.get("username")
                password = auth_config.get("password")
                if username and password:
                    auth = httpx.BasicAuth(username, password)

            # Make request
            method = webhook_config.get("method", "POST").upper()
            timeout = webhook_config.get("timeout_seconds", 30)
            verify_ssl = webhook_config.get("verify_ssl", True)

            async with httpx.AsyncClient(verify=verify_ssl) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=payload,
                    headers=headers,
                    auth=auth,
                    timeout=timeout,
                )

            # Check response
            if 200 <= response.status_code < 300:
                return IntegrationResult(
                    success=True,
                    status=DeliveryStatus.DELIVERED,
                    message=f"Webhook delivered successfully (HTTP {response.status_code})",
                    metadata={
                        "url": url,
                        "status_code": response.status_code,
                        "response_headers": dict(response.headers),
                    },
                )
            elif 400 <= response.status_code < 500:
                # Client error - don't retry
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message=f"Webhook failed with client error (HTTP {response.status_code})",
                    metadata={
                        "url": url,
                        "status_code": response.status_code,
                        "response_text": response.text[:500],  # Truncate response
                    },
                )
            else:
                # Server error - retry
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message=f"Webhook failed with server error (HTTP {response.status_code})",
                    retry_after=120,  # Retry after 2 minutes
                    metadata={
                        "url": url,
                        "status_code": response.status_code,
                        "response_text": response.text[:500],
                    },
                )

        except httpx.TimeoutException:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message="Webhook request timed out",
                retry_after=300,  # Retry after 5 minutes
            )
        except httpx.RequestError as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Webhook request error: {str(e)}",
                retry_after=180,  # Retry after 3 minutes
            )
        except Exception as e:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Unexpected error: {str(e)}",
            )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate webhook configuration."""
        url = config.get("url")
        if not url or not url.startswith(("http://", "https://")):
            return False

        # Validate method
        method = config.get("method", "POST").upper()
        if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            return False

        # Validate timeout
        timeout = config.get("timeout_seconds", 30)
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 300:
            return False

        # Validate auth configuration
        auth_type = config.get("auth_type")
        if auth_type:
            auth_config = config.get("auth_config", {})
            if auth_type == "bearer" and not auth_config.get("token"):
                return False
            elif auth_type == "api_key" and not auth_config.get("api_key"):
                return False
            elif auth_type == "basic" and not (
                auth_config.get("username") and auth_config.get("password")
            ):
                return False

        return True

    async def health_check(self) -> bool:
        """Webhook integration is always available."""
        return True

    def get_required_config_fields(self) -> list[str]:
        """Required webhook configuration fields."""
        return ["url"]

    def get_optional_config_fields(self) -> list[str]:
        """Optional webhook configuration fields."""
        return [
            "method",
            "headers",
            "timeout_seconds",
            "verify_ssl",
            "auth_type",
            "auth_config",
        ]
