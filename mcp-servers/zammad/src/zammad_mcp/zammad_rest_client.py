"""Client for using the Zammad client API directly. Our goal is to avoid this and
pass all requests through the MCP server, however that is not possible for custom attributes
on the user (manager email and current laptop info). as all of the mcp server tools strips those out
"""

import json
from typing import Any, Dict

import httpx
from zammad_mcp.settings import ZAMMAD_MCP_SETTINGS


def _raise_for_zammad_response(r: httpx.Response) -> None:
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise ValueError(
                "Zammad returned 401 Unauthorized. "
                "Confirm ZAMMAD_HTTP_TOKEN matches the token in your "
                "Kubernetes Secret, then `kubectl rollout restart deployment/mcp-zammad-mcp -n <ns>`."
            ) from e
        raise


class ZammadRestClient:
    """Zammad REST: GET /users/{id} only (custom fields not in Basher models)."""

    def __init__(self, base_url: str, http_token: str) -> None:
        self._base = base_url.strip().rstrip("/")
        self._timeout = ZAMMAD_MCP_SETTINGS.mcp_timeout_seconds
        self._headers = {
            "Authorization": f"Token token={http_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _http_client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            timeout=timeout if timeout is not None else self._timeout,
        )

    def get_user(self, user_id: int, timeout: float | None = None) -> Dict[str, Any]:
        with self._http_client(timeout=timeout) as client:
            r = client.get(
                f"{self._base}/api/v1/users/{user_id}",
                headers=self._headers,
            )
            _raise_for_zammad_response(r)
            try:
                data = r.json()
            except json.JSONDecodeError as e:
                raise ValueError(
                    "Zammad REST returned non-JSON (check ZAMMAD_URL / reverse proxy)."
                ) from e
            return dict(data)


def _get_zammad_rest_client(http_token: str | None = None) -> ZammadRestClient:
    """REST client from loaded settings (override ``http_token`` for tests)."""
    base = ZAMMAD_MCP_SETTINGS.zammad_rest_base_url
    if not base:
        raise ValueError("ZAMMAD_URL is required.")
    token = ZAMMAD_MCP_SETTINGS.zammad_http_token if http_token is None else http_token
    if not token:
        raise ValueError(
            "ZAMMAD_HTTP_TOKEN is not set on this process "
            "(Kubernetes secret / local env)."
            if http_token is None
            else "Zammad token is required: set ZAMMAD_HTTP_TOKEN on this process."
        )
    return ZammadRestClient(base_url=base, http_token=token)


def fetch_zammad_customer_user_rest(customer_id: int) -> Dict[str, Any]:
    """``GET /users/{id}`` for custom fields (e.g. manager); call only when Basher auth already passed."""
    try:
        return _get_zammad_rest_client().get_user(customer_id)
    except httpx.RequestError as e:
        raise ValueError(f"Zammad REST: {type(e).__name__}: {e}") from e
