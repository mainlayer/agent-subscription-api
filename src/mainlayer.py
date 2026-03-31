"""Mainlayer API client.

Mainlayer is the monetization layer for AI agents — it handles subscription
billing, entitlement checks, and usage tracking so your agent doesn't have to.

Base URL: https://api.mainlayer.xyz
Auth:     Authorization: Bearer <MAINLAYER_API_KEY>
"""

from __future__ import annotations

import os
from typing import Any

import httpx

try:
    from models import EntitlementResponse, PlanName, SubscribeResponse
except ImportError:
    from src.models import EntitlementResponse, PlanName, SubscribeResponse  # type: ignore[no-redef]


_BASE_URL = "https://api.mainlayer.xyz"
_DEFAULT_TIMEOUT = 10.0


class MainlayerError(Exception):
    """Raised when the Mainlayer API returns an unexpected response."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class MainlayerClient:
    """Async HTTP client for the Mainlayer API."""

    def __init__(
        self,
        api_key: str | None = None,
        resource_id: str | None = None,
        base_url: str = _BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.environ["MAINLAYER_API_KEY"]
        self._resource_id = resource_id or os.environ["RESOURCE_ID"]
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json,
            )
        if response.status_code >= 400:
            raise MainlayerError(
                f"Mainlayer API error {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )
        return response.json()

    # ------------------------------------------------------------------
    # Entitlement
    # ------------------------------------------------------------------

    async def check_entitlement(self, wallet: str) -> EntitlementResponse:
        """Return the subscription entitlement for *wallet* on this resource.

        GET /entitlements/check
            ?resource_id=<id>&wallet=<wallet>
        """
        data = await self._request(
            "GET",
            "/entitlements/check",
            params={"resource_id": self._resource_id, "wallet": wallet},
        )
        return EntitlementResponse(
            active=data.get("active", False),
            wallet=wallet,
            plan=data.get("plan"),
            calls_remaining=data.get("calls_remaining", 0),
            calls_limit=data.get("calls_limit", 0),
        )

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def create_subscription(self, wallet: str, plan: PlanName) -> SubscribeResponse:
        """Create a new subscription for *wallet* on this resource.

        POST /subscriptions
        """
        data = await self._request(
            "POST",
            "/subscriptions",
            json={
                "resource_id": self._resource_id,
                "wallet": wallet,
                "plan": plan.value,
            },
        )
        calls_limit_map = {"starter": 100, "pro": 1000, "unlimited": -1}
        plan_name = PlanName(data.get("plan", plan.value))
        return SubscribeResponse(
            subscription_id=data.get("subscription_id", ""),
            wallet=wallet,
            plan=plan_name,
            status=data.get("status", "pending"),
            calls_remaining=data.get("calls_remaining", calls_limit_map.get(plan.value, 0)),
            checkout_url=data.get("checkout_url"),
        )

    async def get_subscription(self, wallet: str) -> dict[str, Any]:
        """Retrieve the current subscription record for *wallet*.

        GET /subscriptions/:wallet?resource_id=<id>
        """
        return await self._request(
            "GET",
            f"/subscriptions/{wallet}",
            params={"resource_id": self._resource_id},
        )

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    async def record_usage(self, wallet: str, endpoint: str = "/agent/run") -> None:
        """Record one API call for *wallet* against this resource.

        POST /usage
        """
        await self._request(
            "POST",
            "/usage",
            json={
                "resource_id": self._resource_id,
                "wallet": wallet,
                "endpoint": endpoint,
            },
        )

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "MainlayerClient":
        """Create a client from environment variables."""
        return cls(
            api_key=os.environ["MAINLAYER_API_KEY"],
            resource_id=os.environ["RESOURCE_ID"],
        )
