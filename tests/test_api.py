"""tests/test_api.py — Comprehensive test suite for the Agent Subscription API.

Run with:
    pytest tests/test_api.py -v

Requires:
    pytest, pytest-asyncio, httpx, fastapi[all]
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing the app
os.environ.setdefault("MAINLAYER_API_KEY", "test-api-key")
os.environ.setdefault("RESOURCE_ID", "res_test_001")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

# Import after env vars are set
from src.main import app  # noqa: E402
from src.models import EntitlementResponse, PlanName, SubscribeResponse  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


def make_active_entitlement(wallet: str = "wallet-123", plan: str = "pro") -> EntitlementResponse:
    return EntitlementResponse(
        active=True,
        wallet=wallet,
        plan=PlanName(plan),
        calls_remaining=500,
        calls_limit=1000,
    )


def make_inactive_entitlement(wallet: str = "wallet-999") -> EntitlementResponse:
    return EntitlementResponse(
        active=False,
        wallet=wallet,
        plan=None,
        calls_remaining=0,
        calls_limit=0,
    )


def make_subscribe_response(wallet: str = "wallet-123", plan: str = "pro") -> SubscribeResponse:
    return SubscribeResponse(
        subscription_id="sub_abc123",
        wallet=wallet,
        plan=PlanName(plan),
        status="active",
        calls_remaining=1000,
        checkout_url=None,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == status.HTTP_200_OK

    async def test_health_body(self, client: AsyncClient):
        response = await client.get("/health")
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "agent-subscription-api"


# ---------------------------------------------------------------------------
# Capabilities endpoint
# ---------------------------------------------------------------------------


class TestCapabilities:
    async def test_capabilities_returns_200(self, client: AsyncClient):
        response = await client.get("/agent/capabilities")
        assert response.status_code == status.HTTP_200_OK

    async def test_capabilities_name(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        assert body["name"] == "Research Agent"

    async def test_capabilities_has_three_plans(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        assert len(body["plans"]) == 3

    async def test_capabilities_plan_names(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        names = {p["name"] for p in body["plans"]}
        assert names == {"starter", "pro", "unlimited"}

    async def test_capabilities_starter_price(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        starter = next(p for p in body["plans"] if p["name"] == "starter")
        assert starter["price_usd"] == 5.00

    async def test_capabilities_pro_price(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        pro = next(p for p in body["plans"] if p["name"] == "pro")
        assert pro["price_usd"] == 20.00

    async def test_capabilities_unlimited_calls(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        unlimited = next(p for p in body["plans"] if p["name"] == "unlimited")
        assert unlimited["calls_per_month"] == -1

    async def test_capabilities_has_resource_id(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        assert body["resource_id"] == "res_test_001"

    async def test_capabilities_has_expected_capability_types(self, client: AsyncClient):
        body = (await client.get("/agent/capabilities")).json()
        assert set(body["capabilities"]) == {"web_research", "summarization", "fact_checking"}


# ---------------------------------------------------------------------------
# Subscribe endpoint
# ---------------------------------------------------------------------------


class TestSubscribe:
    @patch("src.main.MainlayerClient.from_env")
    async def test_subscribe_success(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.create_subscription.return_value = make_subscribe_response()
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/subscribe", json={"wallet": "wallet-123", "plan": "pro"}
        )
        assert response.status_code == status.HTTP_201_CREATED

    @patch("src.main.MainlayerClient.from_env")
    async def test_subscribe_returns_subscription_id(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.create_subscription.return_value = make_subscribe_response()
        mock_from_env.return_value = mock_client

        body = (
            await client.post("/subscribe", json={"wallet": "wallet-123", "plan": "pro"})
        ).json()
        assert body["subscription_id"] == "sub_abc123"

    @patch("src.main.MainlayerClient.from_env")
    async def test_subscribe_returns_active_status(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.create_subscription.return_value = make_subscribe_response()
        mock_from_env.return_value = mock_client

        body = (
            await client.post("/subscribe", json={"wallet": "wallet-123", "plan": "pro"})
        ).json()
        assert body["status"] == "active"

    async def test_subscribe_invalid_plan_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/subscribe", json={"wallet": "wallet-123", "plan": "enterprise"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_subscribe_missing_wallet_returns_422(self, client: AsyncClient):
        response = await client.post("/subscribe", json={"plan": "pro"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @patch("src.main.MainlayerClient.from_env")
    async def test_subscribe_with_checkout_url(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.create_subscription.return_value = SubscribeResponse(
            subscription_id="sub_xyz",
            wallet="wallet-new",
            plan=PlanName.starter,
            status="pending_payment",
            calls_remaining=0,
            checkout_url="https://pay.mainlayer.xyz/checkout/abc",
        )
        mock_from_env.return_value = mock_client

        body = (
            await client.post("/subscribe", json={"wallet": "wallet-new", "plan": "starter"})
        ).json()
        assert body["checkout_url"].startswith("https://")


# ---------------------------------------------------------------------------
# Agent run endpoint — entitlement checks
# ---------------------------------------------------------------------------


class TestAgentRunEntitlement:
    async def test_missing_wallet_header_returns_400(self, client: AsyncClient):
        response = await client.post(
            "/agent/run",
            json={"task_type": "summarization", "query": "Hello world"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("src.main.MainlayerClient.from_env")
    async def test_inactive_subscription_returns_402(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_inactive_entitlement()
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-999"},
            json={"task_type": "summarization", "query": "Test"},
        )
        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED

    @patch("src.main.MainlayerClient.from_env")
    async def test_402_includes_subscribe_url(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_inactive_entitlement()
        mock_from_env.return_value = mock_client

        body = (
            await client.post(
                "/agent/run",
                headers={"X-Payer-Wallet": "wallet-999"},
                json={"task_type": "summarization", "query": "Test"},
            )
        ).json()
        detail = body.get("detail", body)
        assert "subscribe_url" in detail

    @patch("src.main.MainlayerClient.from_env")
    async def test_active_subscription_returns_200(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "summarization", "query": "Summarize this text."},
        )
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Agent run — task execution
# ---------------------------------------------------------------------------


class TestAgentRunTasks:
    @patch("src.main.MainlayerClient.from_env")
    async def test_web_research_task(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "web_research", "query": "AI agent networks"},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["task_type"] == "web_research"

    @patch("src.main.MainlayerClient.from_env")
    async def test_summarization_task(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "summarization", "query": "Long text to summarize here."},
        )
        body = response.json()
        assert body["task_type"] == "summarization"
        assert "Summary" in body["result"]

    @patch("src.main.MainlayerClient.from_env")
    async def test_fact_checking_task(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "fact_checking", "query": "The Earth is flat."},
        )
        body = response.json()
        assert body["task_type"] == "fact_checking"
        assert "Verdict" in body["result"]

    @patch("src.main.MainlayerClient.from_env")
    async def test_result_contains_query_echo(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        query = "unique-query-string-xyz"
        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "web_research", "query": query},
        )
        body = response.json()
        assert body["query"] == query

    @patch("src.main.MainlayerClient.from_env")
    async def test_invalid_task_type_returns_422(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "nonexistent_task", "query": "Test"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @patch("src.main.MainlayerClient.from_env")
    async def test_empty_query_returns_422(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "summarization", "query": ""},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @patch("src.main.MainlayerClient.from_env")
    async def test_task_options_are_forwarded(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={
                "task_type": "web_research",
                "query": "Quantum computing",
                "options": {"max_results": 5},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["metadata"]["options_applied"]["max_results"] == 5

    @patch("src.main.MainlayerClient.from_env")
    async def test_usage_is_recorded_on_success(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.return_value = None
        mock_from_env.return_value = mock_client

        await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "summarization", "query": "Track me."},
        )
        mock_client.record_usage.assert_called_once_with(
            wallet="wallet-123", endpoint="/agent/run"
        )

    @patch("src.main.MainlayerClient.from_env")
    async def test_usage_tracking_failure_does_not_fail_request(
        self, mock_from_env, client: AsyncClient
    ):
        from src.mainlayer import MainlayerError

        mock_client = AsyncMock()
        mock_client.check_entitlement.return_value = make_active_entitlement()
        mock_client.record_usage.side_effect = MainlayerError("Tracking service unavailable")
        mock_from_env.return_value = mock_client

        response = await client.post(
            "/agent/run",
            headers={"X-Payer-Wallet": "wallet-123"},
            json={"task_type": "summarization", "query": "Resilient call."},
        )
        # Request still succeeds even when usage tracking fails
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Subscription retrieval
# ---------------------------------------------------------------------------


class TestGetSubscription:
    @patch("src.main.MainlayerClient.from_env")
    async def test_get_subscription_calls_mainlayer(self, mock_from_env, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get_subscription.return_value = {
            "wallet": "wallet-123",
            "plan": "pro",
            "status": "active",
        }
        mock_from_env.return_value = mock_client

        response = await client.get("/subscriptions/wallet-123")
        assert response.status_code == status.HTTP_200_OK
        mock_client.get_subscription.assert_called_once_with(wallet="wallet-123")
