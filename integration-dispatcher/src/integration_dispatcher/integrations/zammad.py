"""Zammad integration handler — posts customer-visible ticket articles via REST."""

import os
from typing import Any, Dict

import httpx
from shared_clients.service_client import get_zammad_rest_service_client
from shared_models import configure_logging
from shared_models.models import DeliveryRequest, DeliveryStatus, UserIntegrationConfig
from shared_models.utils import (
    zammad_rest_authorization_headers,
    zammad_rest_json_headers,
)

from .base import BaseIntegrationHandler, IntegrationResult

logger = configure_logging("integration-dispatcher-zammad")


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


def _ticket_article_fallback_on_forbidden() -> bool:
    """Retry POST /ticket_articles without ``From`` after 403 (defaults on). Set to false/0/off to disable."""
    v = os.environ.get("ZAMMAD_TICKET_ARTICLE_FALLBACK_ON_FORBIDDEN")
    if v is None:
        return True
    s = v.strip().lower()
    if s == "":
        return True
    return s in ("1", "true", "yes", "on")


class ZammadIntegrationHandler(BaseIntegrationHandler):
    """Posts pipeline reply body to Zammad, optionally on behalf of assigned owner.

    ``From`` identity prefers the assignee snapshot from the inbound webhook
    (``integration_context`` / normalized request). If the ticket was unassigned
    at intake, the current ticket owner is fetched live so replies match whoever
    claimed the ticket before the agent answered.
    """

    @staticmethod
    def _is_valid_on_behalf_identity(value: str) -> bool:
        v = value.strip()
        if not v:
            return False
        if v in {"-", "n/a", "none", "null", "unknown"}:
            return False
        return True

    async def _live_ticket_owner_email(
        self,
        *,
        client: Any,
        token: str,
        ticket_id: int,
    ) -> str:
        """Current ticket owner from Zammad API (assignee may change after webhook snapshot)."""
        if _env_truthy("ZAMMAD_SKIP_LIVE_TICKET_OWNER_LOOKUP"):
            return ""
        try:
            response = await client.get(
                f"/tickets/{ticket_id}",
                params={"expand": "true"},
                headers=zammad_rest_authorization_headers(token),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return ""

            owner = data.get("owner")
            if isinstance(owner, dict):
                oid = owner.get("id")
                try:
                    if oid is not None and int(oid) <= 1:
                        return ""
                except (TypeError, ValueError):
                    pass
                for key in ("email", "login"):
                    val = owner.get(key)
                    if val and self._is_valid_on_behalf_identity(str(val)):
                        return str(val).strip().lower()

            raw_oid = data.get("owner_id")
            try:
                oid_int = int(raw_oid) if raw_oid is not None else 0
            except (TypeError, ValueError):
                oid_int = 0
            if oid_int <= 1:
                return ""

            uresp = await client.get(
                f"/users/{oid_int}",
                headers=zammad_rest_authorization_headers(token),
            )
            uresp.raise_for_status()
            user_data = uresp.json()
            if isinstance(user_data, dict):
                candidate = str(
                    user_data.get("email") or user_data.get("login") or ""
                ).strip()
                if self._is_valid_on_behalf_identity(candidate):
                    return candidate.lower()
        except Exception as e:
            logger.warning(
                "Zammad live ticket owner lookup failed",
                ticket_id=ticket_id,
                error=str(e),
            )
        return ""

    async def _integration_context_owner_email(
        self,
        *,
        client: Any,
        token: str,
        integration_context: Dict[str, Any],
        ticket_id: int,
    ) -> str:
        """Assignee from the normalized request (webhook snapshot), not live ticket state."""
        owner_email = str(integration_context.get("owner_email") or "").strip().lower()
        if self._is_valid_on_behalf_identity(owner_email):
            return owner_email

        owner_raw = integration_context.get("owner_id")
        try:
            owner_id = int(owner_raw) if owner_raw is not None else 0
        except (TypeError, ValueError):
            owner_id = 0
        if owner_id <= 1:
            return ""

        try:
            response = await client.get(
                f"/users/{owner_id}",
                headers=zammad_rest_authorization_headers(token),
            )
            response.raise_for_status()
            user_data = response.json() if response is not None else {}
            if isinstance(user_data, dict):
                candidate = str(
                    user_data.get("email") or user_data.get("login") or ""
                ).strip()
                if self._is_valid_on_behalf_identity(candidate):
                    return candidate.lower()
        except Exception as e:
            logger.warning(
                "Zammad owner lookup from integration_context failed; "
                "will try live ticket owner",
                ticket_id=ticket_id,
                owner_id=owner_id,
                error=str(e),
            )
        return ""

    async def _resolve_on_behalf_of_email(
        self,
        *,
        client: Any,
        token: str,
        integration_context: Dict[str, Any],
        ticket_id: int,
    ) -> str:
        snapshot = await self._integration_context_owner_email(
            client=client,
            token=token,
            integration_context=integration_context,
            ticket_id=ticket_id,
        )
        if snapshot:
            return snapshot

        live = await self._live_ticket_owner_email(
            client=client, token=token, ticket_id=ticket_id
        )
        if live:
            return live

        return ""

    async def deliver(
        self,
        request: DeliveryRequest,
        config: UserIntegrationConfig,
        template_content: Dict[str, str],
    ) -> IntegrationResult:
        ic = request.integration_context or {}
        if ic.get("delivery_binding") != "TICKET_THREAD":
            return IntegrationResult(
                success=True,
                status=DeliveryStatus.DELIVERED,
                message="Skipped: delivery_binding is not TICKET_THREAD",
                metadata={"delivery_method": "zammad_skip_non_ticket"},
            )

        ticket_raw = ic.get("ticket_id")
        if ticket_raw is None:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message="Missing ticket_id in integration_context",
                metadata={},
            )

        try:
            ticket_id = int(ticket_raw)
        except (TypeError, ValueError):
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Invalid ticket_id in integration_context: {ticket_raw!r}",
                metadata={},
            )

        base_url = (os.getenv("ZAMMAD_URL") or "").strip()
        token = (os.getenv("ZAMMAD_HTTP_TOKEN") or "").strip()
        if not base_url or not token:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message="ZAMMAD_URL or ZAMMAD_HTTP_TOKEN not configured",
                metadata={},
            )

        body = (template_content.get("body") or request.content or "").strip()
        if not body:
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message="Empty delivery body for Zammad article",
                metadata={},
            )

        payload: Dict[str, Any] = {
            "ticket_id": ticket_id,
            "body": body,
            "type": "note",
            "internal": False,
            "sender": "Agent",
        }

        try:
            client = await get_zammad_rest_service_client()
            if client is None:
                return IntegrationResult(
                    success=False,
                    status=DeliveryStatus.FAILED,
                    message="ZAMMAD_URL not configured for pooled REST client",
                    metadata={},
                )
            headers = zammad_rest_json_headers(token)
            on_behalf_of = await self._resolve_on_behalf_of_email(
                client=client,
                token=token,
                integration_context=ic,
                ticket_id=ticket_id,
            )
            if on_behalf_of:
                # Zammad warns X-On-Behalf-Of is deprecated; use From.
                headers["From"] = on_behalf_of
            response = await client.post(
                "/ticket_articles", json=payload, headers=headers
            )
            # If Zammad rejects the From/on-behalf identity (403), optionally retry without From so the article posts as the API token user (same identity as ZAMMAD_HTTP_TOKEN).
            if (
                response.status_code == 403
                and on_behalf_of
                and _ticket_article_fallback_on_forbidden()
            ):
                logger.warning(
                    "Zammad rejected on-behalf article; retrying as token user "
                    "(ZAMMAD_TICKET_ARTICLE_FALLBACK_ON_FORBIDDEN)",
                    ticket_id=ticket_id,
                    on_behalf_of=on_behalf_of,
                )
                fallback_headers = zammad_rest_json_headers(token)
                response = await client.post(
                    "/ticket_articles",
                    json=payload,
                    headers=fallback_headers,
                )
                on_behalf_of = ""
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text[:500]
            except Exception:
                pass
            logger.error(
                "Zammad ticket_articles HTTP error",
                status_code=e.response.status_code,
                detail=detail,
                ticket_id=ticket_id,
            )
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Zammad API error: {e.response.status_code}",
                metadata={"http_status": e.response.status_code, "detail": detail},
            )
        except Exception as e:
            logger.error(
                "Zammad ticket_articles request failed",
                error=str(e),
                ticket_id=ticket_id,
            )
            return IntegrationResult(
                success=False,
                status=DeliveryStatus.FAILED,
                message=f"Zammad request failed: {e!s}",
                metadata={"error": str(e)},
            )

        article_id = data.get("id") if isinstance(data, dict) else None
        return IntegrationResult(
            success=True,
            status=DeliveryStatus.DELIVERED,
            message="Posted customer-visible article to Zammad ticket",
            metadata={
                "delivery_method": "zammad_rest_ticket_articles",
                "zammad_article_id": article_id,
                "ticket_id": ticket_id,
                "responding_agent_id": request.agent_id,
                "on_behalf_of": on_behalf_of or None,
            },
        )

    async def validate_config(self, config: Dict[str, Any]) -> bool:
        return True

    async def health_check(self) -> bool:
        zammad_url = (os.getenv("ZAMMAD_URL") or "").strip()
        zammad_token = (os.getenv("ZAMMAD_HTTP_TOKEN") or "").strip()
        return bool(zammad_url and zammad_token)
