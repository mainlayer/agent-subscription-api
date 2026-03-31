"""Agent Subscription API — FastAPI application entry point.

This service exposes a Research Agent behind a Mainlayer subscription gate.
Other AI agents (or human callers) must hold an active subscription to invoke
/agent/run.  Subscription management happens through /subscribe and the
Mainlayer billing platform.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from agent_logic import execute_agent_task
    from mainlayer import MainlayerClient, MainlayerError
    from models import (
        AgentTask,
        AgentTaskResult,
        CapabilitiesResponse,
        PaymentRequiredPayload,
        Plan,
        PlanName,
        SubscribeRequest,
        SubscribeResponse,
    )
except ImportError:
    from src.agent_logic import execute_agent_task  # type: ignore[no-redef]
    from src.mainlayer import MainlayerClient, MainlayerError  # type: ignore[no-redef]
    from src.models import (  # type: ignore[no-redef]
        AgentTask,
        AgentTaskResult,
        CapabilitiesResponse,
        PaymentRequiredPayload,
        Plan,
        PlanName,
        SubscribeRequest,
        SubscribeResponse,
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent_subscription_api")


# ---------------------------------------------------------------------------
# App lifecycle / DI
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate required environment variables and initialize on startup."""
    required = ("MAINLAYER_API_KEY", "RESOURCE_ID")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    logger.info(
        "Agent Subscription API starting — resource_id=%s",
        os.environ["RESOURCE_ID"],
    )
    logger.info("Endpoints: /health, /agent/capabilities, /subscribe, /agent/run")
    yield
    logger.info("Agent Subscription API shut down.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Research Agent — Subscription API",
    description=(
        "An AI Research Agent that requires an active Mainlayer subscription. "
        "Agents subscribe via POST /subscribe, then call POST /agent/run."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _mainlayer_client() -> MainlayerClient:
    return MainlayerClient.from_env()


def _payment_required_payload() -> dict:
    resource_id = os.environ.get("RESOURCE_ID", "")
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
    return PaymentRequiredPayload(
        subscribe_url=f"{base}/subscribe",
        resource_id=resource_id,
        plans_url=f"{base}/agent/capabilities",
    ).model_dump()


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(MainlayerError)
async def mainlayer_error_handler(request: Request, exc: MainlayerError) -> JSONResponse:
    logger.error("Mainlayer API error: %s (status=%s)", exc, exc.status_code)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "upstream_error", "message": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["meta"])
async def health_check() -> dict:
    """Liveness probe — always returns 200 when the process is alive."""
    return {"status": "ok", "service": "agent-subscription-api"}


@app.get(
    "/agent/capabilities",
    response_model=CapabilitiesResponse,
    tags=["agent"],
    summary="Describe this agent's capabilities and subscription plans.",
)
async def get_capabilities() -> CapabilitiesResponse:
    """Public endpoint — no authentication required.

    Returns the agent's name, supported task types, and available plans so
    that prospective subscribers (human or AI) can choose an appropriate plan.
    """
    return CapabilitiesResponse(
        name="Research Agent",
        capabilities=["web_research", "summarization", "fact_checking"],
        plans=[
            Plan(name=PlanName.starter, calls_per_month=100, price_usd=5.00),
            Plan(name=PlanName.pro, calls_per_month=1000, price_usd=20.00),
            Plan(name=PlanName.unlimited, calls_per_month=-1, price_usd=50.00),
        ],
        resource_id=os.environ.get("RESOURCE_ID", ""),
    )


@app.post(
    "/subscribe",
    response_model=SubscribeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["subscriptions"],
    summary="Subscribe to this agent's capabilities.",
)
async def subscribe(body: SubscribeRequest) -> SubscribeResponse:
    """Create a subscription for the calling agent.

    The caller provides its *wallet* identifier and the desired *plan*.
    Mainlayer returns a checkout URL if payment is still outstanding, or
    activates the subscription immediately for pre-approved wallets.
    """
    client = _mainlayer_client()
    logger.info("Subscription request: wallet=%s plan=%s", body.wallet, body.plan)
    result = await client.create_subscription(wallet=body.wallet, plan=body.plan)
    logger.info(
        "Subscription created: id=%s status=%s", result.subscription_id, result.status
    )
    return result


@app.post(
    "/agent/run",
    response_model=AgentTaskResult,
    tags=["agent"],
    summary="Run an agent task — requires an active subscription.",
    responses={
        402: {
            "description": "Subscription required.",
            "content": {
                "application/json": {
                    "example": {
                        "error": "subscription_required",
                        "message": "An active subscription is required to use this agent.",
                        "subscribe_url": "http://localhost:8000/subscribe",
                        "resource_id": "res_abc123",
                        "plans_url": "http://localhost:8000/agent/capabilities",
                    }
                }
            },
        }
    },
)
async def run_agent(
    task: AgentTask,
    x_payer_wallet: str | None = Header(None, description="The subscriber's wallet identifier."),
) -> AgentTaskResult:
    """Execute an agent task.

    The caller must pass its wallet identifier in the ``X-Payer-Wallet``
    header.  Mainlayer is consulted to verify the subscription is active before
    the task runs.  Each successful call is tracked against the subscription's
    monthly quota.
    """
    if not x_payer_wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_wallet", "message": "X-Payer-Wallet header is required."},
        )

    # 1. Check subscription entitlement via Mainlayer
    client = _mainlayer_client()
    entitlement = await client.check_entitlement(x_payer_wallet)

    if not entitlement.active:
        logger.info("Subscription check failed for wallet=%s", x_payer_wallet)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_payment_required_payload(),
        )

    logger.info(
        "Entitlement confirmed: wallet=%s plan=%s calls_remaining=%s",
        x_payer_wallet,
        entitlement.plan,
        entitlement.calls_remaining,
    )

    # 2. Execute the agent task
    result = await execute_agent_task(task)

    # 3. Record the API call usage (fire-and-forget; non-blocking)
    try:
        await client.record_usage(wallet=x_payer_wallet, endpoint="/agent/run")
    except MainlayerError as exc:
        # Usage tracking failure should not fail the user's request
        logger.warning("Usage tracking failed: %s", exc)

    return result


@app.get(
    "/subscriptions/{wallet}",
    tags=["subscriptions"],
    summary="Retrieve the current subscription for a wallet.",
)
async def get_subscription(wallet: str) -> dict:
    """Return the subscription record for *wallet* on this resource."""
    client = _mainlayer_client()
    return await client.get_subscription(wallet=wallet)
